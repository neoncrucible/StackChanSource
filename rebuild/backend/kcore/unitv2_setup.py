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
from dataclasses import replace


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


def save_address(address, *, root=None):
    """One durable address shared by the installer and every desktop version."""
    from .camera_manager import CameraConfig
    from .storage import default_data_dir
    root = Path(root) if root is not None else default_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    config = CameraConfig.load(root)
    updated = replace(config, address=str(ipaddress.IPv4Address(address)))
    CameraConfig.parse(updated.__dict__).save(root)


def check_existing(address, key, *, client_factory=None):
    """Authenticated status only: no SSH, camera start or pairing mutation."""
    from .unitv2_lifecycle import Client
    from .camera_faults import CameraFault, camera_fault
    if not key: raise CameraFault('pairing_missing')
    try: return (client_factory or Client)(address, key).call('status', timeout=5)
    except Exception as exc: raise camera_fault(exc) from None


def main(address="192.168.40.175"):
    if os.name != "nt": raise RuntimeError("Run setup on the Windows laptop")
    import ctypes
    window = ctypes.windll.kernel32.GetConsoleWindow()
    if window: ctypes.windll.user32.ShowWindow(window, 5)
    print("KADENCE / UNITV2 SETUP\n")
    print("Close the Kadence server and any UnitV2 browser preview first.")
    print("Normal connection reuses saved pairing. App updates do not require this setup.")
    print("Install/repair installs camera lifecycle control and the original face training bridge.")
    print("Existing onboard face profiles and the original service backup are preserved.")
    print("It does not flash firmware or change Wi-Fi. Enter R to restore the original instead.\n")
    operation = input("Check saved connection [Enter], install/repair [I] or restore [R]: ").strip().upper()
    if operation not in {"", "I", "R"}: return 1
    address = str(ipaddress.IPv4Address(input("UnitV2 address ["+address+"]: ").strip() or address))
    from .unitv2_lifecycle import pairing_vault
    vault = pairing_vault()
    saved_key = vault.load().get("unitv2_token")
    if operation == '' and saved_key:
        try:
            status = check_existing(address, saved_key)
            save_address(address)
            print('\nSAVED CONNECTION WORKS. UnitV2 service '+str(status.get('version', 'unknown'))+'.')
            print('No installation or password is needed. Close this window and start Kadence.')
            return 0
        except RuntimeError as exc:
            print('\n'+str(exc))
            print('Saved pairing was kept. Installation/repair is a separate choice, not an app-update step.')
            return 1
        finally: input('\nPress Enter to close. ')
    source = bundle_directory()
    bundle = ("kadence_unitv2.py", "kadence_native.py", "native_faces.html", "native_faces.js", "kadence_tracking.py", "kadence_factory.py")
    for name in (*bundle, "install_unitv2.py"):
        if not (source/name).is_file(): raise RuntimeError("UnitV2 setup files are missing. Extract the complete desktop ZIP.")
    for tool in ("ssh", "scp"):
        if not shutil.which(tool): raise RuntimeError("Install the Windows OpenSSH Client optional feature, then retry.")
    key = saved_key or secrets.token_hex(32)
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
            for name in (*bundle, "install_unitv2.py"): shutil.copyfile(source/name,temporary/name)
            (temporary/"manifest.json").write_text(json.dumps({name:hashlib.sha256((temporary/name).read_bytes()).hexdigest() for name in bundle}))
            (temporary/"kadence-camera.key").write_text(key+"\n")
            subprocess.run(["scp", "-O", *options, *[str(p) for p in temporary.iterdir()], remote+":"+destination+"/"], check=True)
        command = ("sudo python3 "+destination+"/install_unitv2.py"+(" --restore" if operation == "R" else "")
                   + "; kadence_setup_result=$?; rm -f "+destination+"/kadence-camera.key; exit $kadence_setup_result")
        subprocess.run(["ssh", "-t", *options, remote, command], check=True)
        if operation == "R": vault.forget()
        else: save_address(address)
        print("\nSETUP COMPLETE. Unplug UnitV2 power, reconnect it, then start Kadence.")
        print("Kadence will reconnect and check the camera automatically. No manual arming or start/stop test is needed.")
        print("Saved face profiles are retained. Do not repeat setup for a desktop app update.")
        return 0
    finally:
        # Fixed generated path only. Never remove the factory backup.
        subprocess.run(["ssh", "-o", "BatchMode=yes", *options, remote, "rm -f "+destination+"/kadence-camera.key"], check=False)
        input("\nPress Enter to close setup. ")


if __name__ == "__main__": raise SystemExit(main())
