"""Reproducible PlatformIO build, merged flash image and source manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]

def verify_merged_image(image, parts):
    """ROM loads the DIO bootloader; preserve every compiled component verbatim."""
    merged=Path(image).read_bytes()
    boot=Path(parts[0]).read_bytes()
    if len(boot)<24 or boot[0]!=0xe9 or boot[2]!=2:
        raise ValueError('StickS3 ROM bootloader must use a DIO image header')
    if len(merged)<24 or merged[0]!=0xe9 or merged[2]!=2:
        raise ValueError('Merged StickS3 image must retain the DIO ROM boot header')
    for offset,path in parts.items():
        expected=Path(path).read_bytes()
        if merged[offset:offset+len(expected)]!=expected:
            raise ValueError(f'Merged StickS3 component differs at {offset:#x}')
    print('STICKS3_IMAGE PASS rom_mode=DIO compiled_components_preserved=1')

def build(commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Full source commit required')
    source=ROOT/'rebuild'/'sticks3'
    subprocess.run([sys.executable,'-m','platformio','run','-d',str(source)],check=True)
    core=Path.home()/'.platformio'
    output=ROOT/'rebuild'/'dist'/'StickS3';output.mkdir(parents=True,exist_ok=True)
    firmware=source/'.pio'/'build'/'sticks3'
    image=output/'kadence-sticks3.bin'
    parts={0:firmware/'bootloader.bin',0x8000:firmware/'partitions.bin',
        0xe000:core/'packages'/'framework-arduinoespressif32'/'tools'/'partitions'/'boot_app0.bin',
        0x10000:firmware/'firmware.bin'}
    # qio_opi describes runtime flash/PSRAM, not the ROM's initial read mode.
    # Forcing QIO here rewrites the compiler's DIO header and prevents boot.
    subprocess.run([sys.executable,str(core/'packages'/'tool-esptoolpy'/'esptool.py'),'--chip','esp32s3',
        'merge_bin','-o',str(image),'--flash_mode','keep','--flash_freq','keep','--flash_size','keep',
        *[arg for offset,path in parts.items() for arg in (hex(offset),str(path))]],check=True)
    verify_merged_image(image,parts)
    (output/'RELEASE.json').write_text(json.dumps({'device':'StickS3','firmware':'1.0.0','protocol':1,
        'packaging_revision':2,'rom_flash_mode':'dio',
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
