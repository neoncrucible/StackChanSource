"""Interactive installer for the separate StickS3, never the CoreS3 robot."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def main():
    if os.name=='nt':
        import ctypes
        window=ctypes.windll.kernel32.GetConsoleWindow()
        if window:ctypes.windll.user32.ShowWindow(window,5)
    root=Path(sys.executable).parent/'StickS3' if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]/'dist'/'StickS3'
    image=root/'kadence-sticks3.bin'
    manifest=json.loads((root/'RELEASE.json').read_text())
    if manifest.get('device')!='StickS3' or hashlib.sha256(image.read_bytes()).hexdigest()!=manifest['sha256']:
        raise RuntimeError('StickS3 package integrity check failed.')
    print('KADENCE / STICKS3 REMOTE INSTALLER\n')
    print('Unplug the CoreS3 robot USB cable. Connect ONLY the StickS3.\nThis replaces the firmware on the selected Stick. It does not erase the whole flash.\n')
    from serial.tools import list_ports
    for item in list_ports.comports():print(item.device+'  '+str(item.description))
    port=input('\nStickS3 COM port: ').strip()
    if not re.fullmatch(r'COM\d{1,3}',port,re.I):raise ValueError('Enter the StickS3 COM port.')
    if input('Type STICK to flash this device: ').strip()!='STICK':return 1
    import esptool
    esptool.main(['--chip','esp32s3','--port',port,'--baud','460800','write_flash','0x0',str(image)])
    print('\nFlash complete. Reconnect the robot. Start Kadence, then Device -> PAIR STICK VIA USB.\n')
    input('Press Enter to close. ')
    return 0
