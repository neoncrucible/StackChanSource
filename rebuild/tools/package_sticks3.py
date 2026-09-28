"""Reproducible PlatformIO build, merged flash image and source manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]

def build(commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Full source commit required')
    source=ROOT/'rebuild'/'sticks3'
    subprocess.run([sys.executable,'-m','platformio','run','-d',str(source)],check=True)
    core=Path.home()/'.platformio'
    output=ROOT/'rebuild'/'dist'/'StickS3';output.mkdir(parents=True,exist_ok=True)
    firmware=source/'.pio'/'build'/'sticks3'
    image=output/'kadence-sticks3.bin'
    subprocess.run([sys.executable,str(core/'packages'/'tool-esptoolpy'/'esptool.py'),'--chip','esp32s3',
        'merge_bin','-o',str(image),'--flash_mode','qio','--flash_freq','80m','--flash_size','8MB',
        '0x0',str(firmware/'bootloader.bin'),'0x8000',str(firmware/'partitions.bin'),
        '0xe000',str(core/'packages'/'framework-arduinoespressif32'/'tools'/'partitions'/'boot_app0.bin'),
        '0x10000',str(firmware/'firmware.bin')],check=True)
    (output/'RELEASE.json').write_text(json.dumps({'device':'StickS3','firmware':'1.0.0','protocol':1,
        'source_commit':commit,'flash_offset':'0x0','sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
        'physical_signoff':False},indent=2)+'\n')
    shutil.copyfile(ROOT/'rebuild'/'docs'/'STICKS3_REMOTE_0_4_14.md',output/'STICKS3-REMOTE.txt')
    shutil.copyfile(source/'platformio.ini',output/'platformio.ini')
    notices=output/'ThirdParty';notices.mkdir(exist_ok=True)
    for library in (source/'.pio'/'libdeps'/'sticks3').iterdir():
        if library.is_dir():
            for file in library.iterdir():
                if file.is_file() and file.name.lower().startswith(('license','copying','notice')):
                    target=notices/library.name;target.mkdir(exist_ok=True);shutil.copyfile(file,target/file.name)
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-commit',required=True)
    print(build(parser.parse_args().source_commit))
