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


def combine(desktop: Path, firmware: Path, commit: str, output: Path):
    release=json.loads((firmware/'RELEASE.json').read_text())
    if release['source_commit'] != commit: raise ValueError('Desktop and firmware commits differ')
    if not (desktop/'Kadence.exe').is_file(): raise ValueError('Windows executable is missing')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(desktop,output,dirs_exist_ok=True)
    shutil.copytree(firmware,output/'Firmware')
    for name in ('USER_MANUAL.md','RC2_ENGINEERING.md'):
        shutil.copyfile(ROOT/'rebuild'/'docs'/name,output/name)
    shutil.copyfile(ROOT/'rebuild'/'tools'/'flash_desktop.ps1',output/'Flash-Kadence.ps1')
    (output/'RELEASE.json').write_text(json.dumps({'format':1,'candidate':'Kadence RC2',
        'host_version':'0.3.1','firmware_version':'0.21.2','source_commit':commit,
        'physical_signoff':False,'entry':'Kadence.exe'},indent=2)+'\n')
    (output/'START-HERE.txt').write_text(
        'KADENCE RC2\n\nExtract the entire ZIP to a new folder.\n'
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
        'RC2 is a hardware qualification candidate. The approved RC1 remains your rollback build.\n')
    sums=[]
    for file in sorted(output.rglob('*')):
        if file.is_file(): sums.append(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+file.relative_to(output).as_posix())
    (output/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
    archive=output.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(output.rglob('*')):
            if file.is_file(): z.write(file,file.relative_to(output))
    return archive


def build(commit: str, firmware: Path):
    if sys.platform!='win32': raise RuntimeError('Build the Windows package on Windows')
    if not re.fullmatch('[0-9a-f]{40}',commit): raise ValueError('Full source commit required')
    work=ROOT/'rebuild'/'dist'/('desktop-build-'+commit[:12])
    work.mkdir(parents=True,exist_ok=True)
    entry=work/'desktop_entry.py'
    entry.write_text('from kcore.desktop import main\nif __name__ == "__main__": raise SystemExit(main())\n')
    (work/'BUILD.json').write_text(json.dumps({'source_commit':commit,'host_version':'0.3.1'}))
    # Keep standard streams for the same executable's private worker mode.
    # hide-early hides the bootloader's window, without disabling stdin/stdout.
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
        '--onedir','--name','Kadence','--console','--hide-console','hide-early',
        '--distpath',str(work/'app'),'--workpath',str(work/'objects'),'--specpath',str(work),
        '--collect-submodules','kcore','--collect-data','tzdata','--collect-data','certifi',
        '--collect-all','cv2','--hidden-import','_cffi_backend',
        '--add-data',str(work/'BUILD.json')+os.pathsep+'.',str(entry)],cwd=ROOT,check=True)
    desktop=work/'app'/'Kadence'
    notices=desktop/'ThirdParty'; notices.mkdir(exist_ok=True)
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
    subprocess.run([sys.executable,str(ROOT/'rebuild'/'tools'/'desktop_frozen_check.py'),str(desktop/'Kadence.exe'),commit],check=True)
    return combine(desktop,firmware,commit,ROOT/'rebuild'/'dist'/('Kadence-RC2-'+commit[:12]))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--firmware',type=Path,required=True)
    args=parser.parse_args()
    print(build(args.source_commit,args.firmware))
