"""One-time Windows setup using the user's OpenSSH host trust and password prompt."""
from __future__ import annotations
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile


# Factory devtmpfs can recreate /dev/null as root:root 0660 after reboot.
# SCP needs normal-user access. Check the opened Linux null device itself
# before changing its standard permissions; never follow a replacement symlink.
NULL_DEVICE_PREFLIGHT = """import os, stat
fd = os.open('/dev/null', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    info = os.fstat(fd)
    if not stat.S_ISCHR(info.st_mode) or info.st_rdev != os.makedev(1, 3):
        raise SystemExit('Unexpected /dev/null device; no changes made')
    if stat.S_IMODE(info.st_mode) != 0o666:
        os.fchmod(fd, 0o666)
        print('Corrected UnitV2 /dev/null permissions for file transfer.', flush=True)
finally:
    os.close(fd)
"""


def preparation_command(destination):
    return ("sudo python3 -c " + shlex.quote(NULL_DEVICE_PREFLIGHT)
            + " && test -r /dev/null && test -w /dev/null"
            + " && umask 077 && mkdir " + shlex.quote(destination))


def bundle_directory():
    if getattr(sys, "frozen", False): return Path(sys.executable).parent/"UnitV2"
    return Path(__file__).resolve().parents[2]/"unitv2"


def launch(address):
    if os.name != "nt": raise RuntimeError("UnitV2 setup uses Windows OpenSSH.")
    address = str(ipaddress.IPv4Address(address))
    command = [sys.executable]
    if not getattr(sys,"frozen",False): command += ["-m", "kcore.desktop"]
    subprocess.Popen(command+["--unitv2-setup", address], creationflags=subprocess.CREATE_NEW_CONSOLE)


def main(address="192.168.40.175"):
    if os.name != "nt": raise RuntimeError("Run setup on the Windows laptop")
    import ctypes
    window = ctypes.windll.kernel32.GetConsoleWindow()
    if window: ctypes.windll.user32.ShowWindow(window, 5)
    print("KADENCE / UNITV2 SETUP\n")
    print("Close the Kadence server and any UnitV2 browser preview first.")
    print("This backs up the original service and installs camera start/stop control.")
    print("It does not flash firmware or change Wi-Fi. Enter R to restore the original instead.\n")
    operation = input("Install [Enter] or restore [R]: ").strip().upper()
    if operation not in {"", "R"}: return 1
    address = str(ipaddress.IPv4Address(input("UnitV2 address ["+address+"]: ").strip() or address))
    source = bundle_directory()
    for name in ("kadence_unitv2.py", "install_unitv2.py"):
        if not (source/name).is_file(): raise RuntimeError("UnitV2 setup files are missing. Extract the complete desktop ZIP.")
    for tool in ("ssh", "scp"):
        if not shutil.which(tool): raise RuntimeError("Install the Windows OpenSSH Client optional feature, then retry.")
    from .unitv2_lifecycle import pairing_vault
    vault = pairing_vault()
    key = vault.load().get("unitv2_token") or secrets.token_hex(32)
    # Save before remote changes so interruption cannot lose the newly installed key.
    if operation != "R": vault.save({"unitv2_token":key})
    remote = "m5stack@"+address
    destination = "/tmp/kadence-setup-"+secrets.token_hex(8)
    options = ["-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=ask"]
    print("\nOpenSSH will ask for the UnitV2 password; Kadence does not store it.")
    print("If it asks about the host fingerprint, compare it with your existing UnitV2 SSH connection.")
    print("Setup checks the camera's /dev/null permissions before copying files; sudo may ask for the same password.")
    try:
        subprocess.run(["ssh", "-t", *options, remote, preparation_command(destination)], check=True)
        with tempfile.TemporaryDirectory(prefix="kadence-unitv2-") as folder:
            temporary = Path(folder)
            for name in ("kadence_unitv2.py", "install_unitv2.py"): shutil.copyfile(source/name,temporary/name)
            (temporary/"manifest.json").write_text(json.dumps({"kadence_unitv2.py":hashlib.sha256((temporary/"kadence_unitv2.py").read_bytes()).hexdigest()}))
            (temporary/"kadence-camera.key").write_text(key+"\n")
            subprocess.run(["scp", "-O", *options, *[str(p) for p in temporary.iterdir()], remote+":"+destination+"/"], check=True)
        command = "sudo python3 "+destination+"/install_unitv2.py"+(" --restore" if operation == "R" else "")
        subprocess.run(["ssh", "-t", *options, remote, command], check=True)
        if operation == "R": vault.forget()
        print("\nSETUP COMPLETE. Unplug UnitV2 power, reconnect it, then start Kadence.")
        print("In Vision select ON DEMAND and click TEST START / STOP. No robot firmware flash is needed.")
        return 0
    finally:
        # Fixed generated path only. Never remove the factory backup.
        subprocess.run(["ssh", *options, remote, "rm -f "+destination+"/kadence-camera.key"], check=False)
        input("\nPress Enter to close setup. ")


if __name__ == "__main__": raise SystemExit(main())
