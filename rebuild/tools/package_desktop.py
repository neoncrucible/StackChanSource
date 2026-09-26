"""Build a self-contained Windows console and combine its matching firmware."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
HOST_VERSION='0.4.4'


def archive_package(output: Path):
    sums=[]
    for file in sorted(output.rglob('*')):
        if file.is_file(): sums.append(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(output).as_posix())
    (output/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
    archive=Path(str(output)+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(output.rglob('*')):
            if file.is_file(): z.write(file,file.relative_to(output))
    return archive


def host_package(desktop: Path, commit: str, output: Path):
    if not (desktop/'Kadence.exe').is_file(): raise ValueError('Windows executable is missing')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(desktop,output,dirs_exist_ok=True)
    for name in ('Install-Kadence.cmd','install_desktop.ps1'):
        shutil.copyfile(ROOT/'rebuild'/'tools'/name,output/name)
    shutil.copyfile(ROOT/'rebuild'/'docs'/'DESKTOP_INSTALL_UPDATE.md',output/'START-HERE.txt')
    shutil.copyfile(ROOT/'rebuild'/'docs'/'CAMERA_PERCEPTION.md',output/'CAMERA-PERCEPTION.txt')
    shutil.copyfile(ROOT/'rebuild'/'docs'/'REFLEX_OBSERVATION.md',output/'REFLEX-OBSERVATION.txt')
    shutil.copyfile(ROOT/'rebuild'/'docs'/'VOICE_LATENCY.md',output/'VOICE-LATENCY.txt')
    shutil.copyfile(ROOT/'rebuild'/'docs'/'UNITV2_LIFECYCLE.md',output/'UNITV2-START-STOP.txt')
    shutil.copytree(ROOT/'rebuild'/'unitv2',output/'UnitV2',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (output/'RELEASE.json').write_text(json.dumps({'format':1,'package_kind':'desktop-host',
        'host_version':HOST_VERSION,'source_commit':commit,'entry':'Kadence.exe',
        'firmware_included':False,'compatible_firmware':['0.21.6'],
        'physical_signoff':False},indent=2)+'\n')
    return archive_package(output)


def combine(desktop: Path, firmware: Path, commit: str, output: Path):
    release=json.loads((firmware/'RELEASE.json').read_text())
    if release['source_commit'] != commit: raise ValueError('Desktop and firmware commits differ')
    if not (desktop/'Kadence.exe').is_file(): raise ValueError('Windows executable is missing')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(desktop,output,dirs_exist_ok=True)
    shutil.copytree(firmware,output/'Firmware')
    for name in ('USER_MANUAL.md','RC2_ENGINEERING.md','SENSOR_BUS_PHASE1.md','GESTURE_PERSONA_AUDIO.md','TOF4M_BRINGUP.md'):
        shutil.copyfile(ROOT/'rebuild'/'docs'/name,output/name)
    shutil.copyfile(ROOT/'rebuild'/'tools'/'flash_desktop.ps1',output/'Flash-Kadence.ps1')
    (output/'RELEASE.json').write_text(json.dumps({'format':1,'candidate':'Kadence RC2',
        'host_version':HOST_VERSION,'firmware_version':'0.21.6','source_commit':commit,
        'physical_signoff':False,'compatible_firmware':['0.21.2','0.21.3','0.21.4','0.21.5','0.21.6'],'entry':'Kadence.exe'},indent=2)+'\n')
    (output/'START-HERE.txt').write_text(
        f'KADENCE RC2 / SIGNAL CONSOLE {HOST_VERSION}\n\nExtract the entire ZIP to a new folder.\n'
        'GESTURE / TOF4M RANGING / FIRMWARE 0.21.6:\n'
        'The new sensor diagnostics require flashing the bundled firmware.\n'
        'Read TOF4M_BRINGUP.md for distance checks. Read GESTURE_PERSONA_AUDIO.md for wiring, persona, Ollama and Windows audio.\n'
        'Keep the hub at 0x70; Gesture on channel 0, ToF4M on channel 1.\n\n'
        'INSTALL THE CANDIDATE:\n'
        '1. Close any running Kadence server and serial monitor.\n'
        '2. Put the robot in download mode. In PowerShell here, run:\n'
        '   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\Flash-Kadence.ps1 -Port COM4\n'
        '   The flash helper uses your existing ESP-IDF 5.5.4 installation.\n'
        '3. Restart the robot normally if it remains in download mode.\n'
        '4. Open Kadence.exe, enter the connection fields and click START SERVER.\n'
        '   Daily operation needs no Python or ESP-IDF terminal.\n'
        '5. Keep USB connected to the awake PC while using the robot.\n'
        '6. Tap once, wait for the cue and REC countdown, then speak.\n\n'
        'Read USER_MANUAL.md for reminders, workbench, vision and top controls.\n'
        'Physical sign-off is pending. Keep the camera-tested 038f203eb094 firmware available.\n')
    return archive_package(output)


def build(commit: str, firmware: Path | None = None):
    if sys.platform!='win32': raise RuntimeError('Build the Windows package on Windows')
    if not re.fullmatch('[0-9a-f]{40}',commit): raise ValueError('Full source commit required')
    work=ROOT/'rebuild'/'dist'/('desktop-build-'+commit[:12])
    work.mkdir(parents=True,exist_ok=True)
    entry=work/'desktop_entry.py'
    entry.write_text('from kcore.desktop import main\nif __name__ == "__main__": raise SystemExit(main())\n')
    (work/'BUILD.json').write_text(json.dumps({'source_commit':commit,'host_version':HOST_VERSION}))
    from prepare_face_models import prepare
    model_dir=prepare(ROOT/'rebuild'/'dist'/'face_models')
    # Keep standard streams for the same executable's private worker mode.
    # hide-early hides the bootloader's window, without disabling stdin/stdout.
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
        '--onedir','--name','Kadence','--console','--hide-console','hide-early',
        '--distpath',str(work/'app'),'--workpath',str(work/'objects'),'--specpath',str(work),
        '--collect-submodules','kcore','--collect-data','tzdata','--collect-data','certifi',
        # Let PyInstaller's maintained cv2 hook collect the OpenCV loader, extension,
        # config files, and numpy dependencies.  ``--collect-all cv2`` duplicates that
        # collection and can leave the frozen Windows loader blocked during ``import cv2``.
        '--runtime-hook',str(ROOT/'rebuild'/'tools'/'pyi_rth_cv2.py'),
        '--hidden-import','_cffi_backend',
        '--add-data',str(model_dir)+os.pathsep+'face_models',
        '--add-data',str(work/'BUILD.json')+os.pathsep+'.',str(entry)],cwd=ROOT,check=True)
    desktop=work/'app'/'Kadence'
    notices=desktop/'ThirdParty'; notices.mkdir(exist_ok=True)
    shutil.copytree(ROOT/'rebuild'/'backend'/'kcore'/'model_notices',notices/'OpenCV-Zoo')
    versions={}
    for dist in importlib.metadata.distributions():
        name=dist.metadata.get('Name','unknown'); versions[name]=dist.version
        for file in dist.files or ():
            if any(word in str(file).casefold() for word in ('license','copying','notice')):
                source=Path(dist.locate_file(file))
                if source.is_file() and source.stat().st_size<2*1024*1024:
                    dest=notices/re.sub('[^A-Za-z0-9_.-]','_',name)/Path(str(file)).name
                    dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,dest)
    (notices/'versions.json').write_text(json.dumps(versions,indent=2)+'\n')
    (notices/'README.txt').write_text(
        'Kadence uses unmodified shared Qt/PySide6 libraries under their supplied open-source terms.\n'
        'Licences are collected below; replaceable libraries are in _internal.\n'
        'Qt source: https://download.qt.io/official_releases/qt/\n'
        'PySide6 source: https://code.qt.io/cgit/pyside/pyside-setup.git/\n'
        'Kadence source: https://github.com/neoncrucible/StackChanSource/tree/kadence/rebuild-kade\n')
    subprocess.run([sys.executable,str(ROOT/'rebuild'/'tools'/'desktop_frozen_check.py'),str(desktop/'Kadence.exe'),commit,'--offline'],check=True)
    if firmware is None:
        return host_package(desktop,commit,ROOT/'rebuild'/'dist'/('Kadence-Desktop-'+HOST_VERSION+'-'+commit[:12]))
    return combine(desktop,firmware,commit,ROOT/'rebuild'/'dist'/('Kadence-RC2-'+commit[:12]))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-commit',required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--firmware',type=Path)
    mode.add_argument('--host-only',action='store_true')
    args=parser.parse_args()
    print(build(args.source_commit,args.firmware))
