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
TRACKER_SHA256 = '0cec301c02f8ab75bccedeedafef38758f3bf1ff931624683609b3cf315ed112'
FACTORY_BINARIES = {
    'color_tracker':'bdd4b7f29bc8d76bd98e20179bef666908301e66661ca446648302af69d6ff3b',
    'shape_detector':'afb467c9852cb783d9d1ca63029e2e2293fa45a66c9b42861a1592638ba5186b',
    'shape_matching':'df494ddf1938ac5aeedd5d74c6df94ea89940cee5629f95909d914691ca285e2',
    'motion_tracker':'3b3358561abd9b43b1ce0ab159ef1b4f925476ef99acd15355c0f5c3941d761d',
    'code_detector':'760862251a94bebb1c046802b43680b74ea2815dfe029de2124380d9e28d5a30',
    'object_recognition':'7e478f8331b12b18b7ec06cce303337750abc899b87a011ac67fffc6a12652a0',
    'face_detector':'de713eded09a4797caecade29a5d68975df363960dbc324b51537d5e92aa3a5b',
    'lane_line_tracker':'e9e64bb0d100f45c066814de79dfeeba7947e7fe037e012beedf752d2585cc40',
    'online_classifier':'b9928700725d57a872e4a0db6abd573ccd90cf0993b6828eb810688de92c39a6',
    'audio_fft':'56d13d22fc36d23e156e72a7b7048027e3c4208539ea360eb8d6c3259e9c5068',
}
BUNDLE = ('kadence_unitv2.py', 'kadence_native.py', 'native_faces.html', 'native_faces.js', 'kadence_tracking.py', 'kadence_factory.py')
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
    tracker = root/'bin'/'target_tracker'
    if tracker.is_symlink() or digest(tracker) != TRACKER_SHA256:
        raise RuntimeError('Unsupported factory target tracker; no changes made')
    # Optional factory algorithms are discovered by the running service. A
    # recovery image may legitimately omit a model-specific binary; setup must
    # still preserve the accepted camera/face/tracker lifecycle in that case.
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
