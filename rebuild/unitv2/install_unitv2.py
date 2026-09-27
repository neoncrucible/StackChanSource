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
import uuid

FACTORY_SHA256 = "4cbdcc26903effc52638e0a85e7c463991087235e8b4e70d64b35e150ba05d74"
CAMERA_SHA256 = "a2203a4700445ee62feec8e5c645cf6ae05211e01ba2153ce555519f62f20b92"
FACE_SHA256 = "00012bd3cda05f4fc482542830822f9bb15fe3c1a23794a106edf206ec13fd99"
BUNDLE = ('kadence_unitv2.py', 'kadence_native.py', 'native_faces.html', 'native_faces.js')
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
    if manifest != {name: digest(source/name) for name in BUNDLE}: raise RuntimeError("Service bundle checksum mismatch")
    for name in BUNDLE:
        if name.endswith('.py'): compile((source/name).read_bytes(), name, "exec")
    face = root/'bin'/'face_recognition'
    if face.is_symlink() or digest(face) != FACE_SHA256: raise RuntimeError('Unsupported factory recognition binary; no changes made')
    for name in ('js/jquery.min.js', 'js/bin/face_recognition.js', 'js/core/post.server.js'):
        asset = root/'static'/name
        if not asset.is_file() or asset.is_symlink(): raise RuntimeError('Factory training web files are missing; no changes made')
    key = (source/"kadence-camera.key").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", key): raise RuntimeError("Invalid pairing key; no changes made")
    for target in [root/name for name in BUNDLE] + [root/"kadence-camera.key",root/'kadence-device.id']:
        if target.is_symlink(): raise RuntimeError("Unexpected symlink; no changes made")
    identity = root/'kadence-device.id'
    if identity.exists() and not re.fullmatch(r'[0-9a-f]{32}',identity.read_text().strip()):
        raise RuntimeError('UnitV2 identity differs; no changes made')
    if not backup.exists(): atomic(backup, current, 0o444)
    if not identity.exists(): atomic(identity,(uuid.uuid4().hex+'\n').encode(),0o600)
    atomic(root/"kadence-camera.key", (key+"\n").encode(), 0o600)
    # Existing installations already import kadence_unitv2 at boot. Install all
    # of its new dependencies before replacing that live entry module.
    for name in BUNDLE[1:]: atomic(root/name,(source/name).read_bytes(),0o644)
    atomic(root/BUNDLE[0],(source/BUNDLE[0]).read_bytes(),0o644)
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
