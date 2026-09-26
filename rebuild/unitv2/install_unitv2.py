"""Atomic, reversible service install. Run on UnitV2 with sudo python3.

Refuses every unknown factory build. Never flashes, changes Wi-Fi, or kills
processes. Power-cycle after install/restore to start the selected service.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

FACTORY_SHA256 = "4cbdcc26903effc52638e0a85e7c463991087235e8b4e70d64b35e150ba05d74"
CAMERA_SHA256 = "a2203a4700445ee62feec8e5c645cf6ae05211e01ba2153ce555519f62f20b92"
SHIM = b"# Kadence UnitV2 lifecycle service; factory entry is backed up.\nfrom kadence_unitv2 import main\nif __name__ == '__main__': main()\n"


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path, data, mode):
    temporary = path.with_name(path.name+".kadence-tmp")
    # O_EXCL refuses a pre-existing file or symlink.
    fd = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists(): temporary.unlink()


def install(root, source, *, restore=False):
    root, source = Path(root), Path(source)
    entry, backup = root/"server_core.py", root/"server_core.kadence-original.py"
    binary = root/"bin"/"camera_stream"
    if entry.is_symlink() or backup.is_symlink() or binary.is_symlink(): raise RuntimeError("Unexpected symlink; no changes made")
    if digest(binary) != CAMERA_SHA256: raise RuntimeError("Unsupported camera binary; no changes made")
    current = entry.read_bytes()
    if current != SHIM and hashlib.sha256(current).hexdigest() != FACTORY_SHA256:
        raise RuntimeError("Factory service has changed; no changes made. Send the setup error for review.")
    if backup.exists() and digest(backup) != FACTORY_SHA256: raise RuntimeError("Original backup differs; no changes made")
    if restore:
        if not backup.exists(): raise RuntimeError("Original backup is missing; no changes made")
        atomic(entry, backup.read_bytes(), 0o644)
        return {"result": "restored", "restart": "power_cycle_unitv2"}
    # Validate the complete bundle before changing a single installed file.
    manifest = json.loads((source/"manifest.json").read_text())
    code = source/"kadence_unitv2.py"
    if manifest != {"kadence_unitv2.py": digest(code)}: raise RuntimeError("Service bundle checksum mismatch")
    compile(code.read_bytes(), str(code), "exec")
    key = (source/"kadence-camera.key").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", key): raise RuntimeError("Invalid pairing key; no changes made")
    for target in (root/"kadence_unitv2.py", root/"kadence-camera.key"):
        if target.is_symlink(): raise RuntimeError("Unexpected symlink; no changes made")
    if not backup.exists(): atomic(backup, current, 0o444)
    atomic(root/"kadence_unitv2.py", code.read_bytes(), 0o644)
    atomic(root/"kadence-camera.key", (key+"\n").encode(), 0o600)
    # Switch entry point last. Original supervisor and network setup are intact.
    atomic(entry, SHIM, 0o644)
    return {"result": "installed", "restart": "power_cycle_unitv2", "original_sha256": FACTORY_SHA256}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0: raise SystemExit("Run with sudo python3 install_unitv2.py")
    try: print(json.dumps(install("/home/m5stack/payload", Path(__file__).resolve().parent, restore=args.restore)))
    except Exception as exc: raise SystemExit(str(exc))
