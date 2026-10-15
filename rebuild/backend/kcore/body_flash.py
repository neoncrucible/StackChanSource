"""One-time CoreS3 updater shipped with the matching host; never an auto-flash."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def verified_files(root: Path, commit: str):
    release=json.loads((root/'RELEASE.json').read_text())
    manifest=json.loads((root/'flasher_args.json').read_text())
    if (release.get('source_commit')!=commit or release.get('device')!='CoreS3-StackChan'
            or release.get('firmware_version')!='0.21.7' or release.get('chip')!='esp32s3'
            or release.get('flash_size')!='16MB'):
        raise ValueError('This firmware does not match the CoreS3 release. Extract the complete update again.')
    if manifest.get('extra_esptool_args',{}).get('chip')!='esp32s3':
        raise ValueError('Incorrect firmware target.')
    settings=manifest.get('flash_settings',{})
    if settings.get('flash_mode') not in {'qio','dio'} or settings.get('flash_freq')!='80m' or settings.get('flash_size')!='16MB':
        raise ValueError('Incorrect flash geometry.')
    files=manifest.get('flash_files',{})
    offsets={int(offset,0) for offset in files}
    limits={0:0x8000,0x8000:0x1000,0xd000:0x2000,0x10000:0x400000}
    if not {0,0x8000,0x10000} <= offsets or not offsets <= limits.keys() or len(offsets)!=len(files):
        raise ValueError('Flash regions would overlap saved settings; update refused.')
    checked=[]
    for offset, relative in files.items():
        name=PurePosixPath(relative)
        if name.is_absolute() or '..' in name.parts or ':' in relative or '\\' in relative:
            raise ValueError('Invalid firmware file path.')
        path=(root/relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('A firmware image is missing.')
        data=path.read_bytes(); entry=release.get('files',{}).get(relative,{})
        if (not 0<len(data)<=limits[int(offset,0)] or entry.get('offset')!=offset
                or entry.get('bytes')!=len(data) or hashlib.sha256(data).hexdigest()!=entry.get('sha256')):
            raise ValueError('Firmware integrity check failed. No device was changed.')
        checked.append((int(offset,0),path))
    return settings,sorted(checked)


def flash(root, commit, port, backup_root, *, runner=None):
    """Validate before connecting; back up NVS and never write its region."""
    settings,files=verified_files(root,commit)
    if not re.fullmatch(r'COM[1-9]\d{0,2}',port,re.I): raise ValueError('Choose the robot USB port.')
    if runner is None:
        import esptool
        runner=esptool.main
    from datetime import datetime, timezone
    backup=backup_root/datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True,exist_ok=False)
    common=['--chip','esp32s3','--port',port,'--baud','460800']
    before=backup/'nvs-before.bin'
    runner(common+['--after','no_reset','read_flash','0x9000','0x4000',str(before)])
    if not before.is_file() or before.stat().st_size!=0x4000:
        raise ValueError('Could not back up robot settings. Firmware was not written.')
    args=common+['--after','no_reset','write_flash','--flash_mode',settings['flash_mode'],'--flash_freq','80m','--flash_size','16MB']
    for offset,path in files: args.extend([hex(offset),str(path)])
    runner(args) # esptool verifies every written image; no erase_flash command.
    after=backup/'nvs-after.bin'
    runner(common+['read_flash','0x9000','0x4000',str(after)])
    if not after.is_file() or before.read_bytes()!=after.read_bytes():
        raise RuntimeError('Firmware was written, but saved-settings verification failed. Keep the backup and do not reset settings.')
    (backup/'update.json').write_text(json.dumps({'source_commit':commit,'firmware_version':'0.21.7','settings_preserved':True})+'\n')
    return backup


def main():
    from PySide6.QtCore import QLockFile, QThread, Signal
    from PySide6.QtWidgets import QApplication, QDialog, QLabel, QComboBox, QPushButton, QPlainTextEdit, QVBoxLayout, QMessageBox
    from .context_store import default_data_dir
    from .build_info import build_info
    from serial.tools import list_ports
    from contextlib import redirect_stdout, redirect_stderr
    app=QApplication(sys.argv[:1]); directory=default_data_dir(); directory.mkdir(parents=True,exist_ok=True)
    app.setStyleSheet('QDialog{background:#11181f;color:#e2eaf0} QLabel{color:#e2eaf0} QComboBox,QPlainTextEdit{background:#19232d;color:#e2eaf0;border:1px solid #344451;padding:8px} QPushButton{background:#70d9ce;color:#0b2023;border:0;border-radius:6px;padding:12px;font-weight:600} QPushButton:disabled{background:#344451;color:#9aa9b6}')
    lock=QLockFile(str(directory/'desktop.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None,'Close Kadence','Quit Kadence from the tray, then run Update-Robot again.');return 1
    root=Path(sys.executable).parent/'Firmware'
    commit=build_info()['source_commit']
    try:verified_files(root,commit)
    except (ValueError,OSError,KeyError) as exc:
        QMessageBox.critical(None,'Update unavailable',str(exc));lock.unlock();return 1

    class Worker(QThread):
        log=Signal(str);result=Signal(bool,str)
        def __init__(self,port):super().__init__();self.port=port
        def write(self,text):self.log.emit(str(text));return len(text)
        def flush(self):pass
        def run(self):
            try:
                with redirect_stdout(self),redirect_stderr(self):
                    backup=flash(root,commit,self.port,directory/'firmware-backups')
                self.result.emit(True,'Update complete. Saved robot settings verified.\nRestart the robot, then open Kadence.\nBackup: '+str(backup))
            except (Exception,SystemExit) as exc:self.result.emit(False,'Update did not complete: '+str(exc)+'\nKeep this window open if you need the log.')

    class Window(QDialog):
        def __init__(self):
            super().__init__();self.busy=False;self.worker=None
            self.setWindowTitle('Kadence · Robot update');self.resize(640,470)
            layout=QVBoxLayout(self)
            title=QLabel('Natural speech · CoreS3 0.21.7');title.setStyleSheet('font-size:22px;font-weight:600');layout.addWidget(title)
            note=QLabel('Connect only the CoreS3 / StackChan robot by USB. Unplug any StickS3.\nThis update ends recording when you stop speaking and preserves saved settings.');note.setWordWrap(True);layout.addWidget(note)
            self.ports=QComboBox()
            for item in list_ports.comports():self.ports.addItem(item.device+' · '+str(item.description),item.device)
            layout.addWidget(self.ports)
            self.start=QPushButton('Update robot');self.start.setEnabled(self.ports.count()>0);layout.addWidget(self.start)
            self.status=QLabel('Choose the robot USB port. Keep USB connected throughout the update.');self.status.setWordWrap(True);layout.addWidget(self.status)
            self.log=QPlainTextEdit();self.log.setReadOnly(True);layout.addWidget(self.log)
            self.start.clicked.connect(self.begin_update)
        def begin_update(self):
            self.busy=True;self.start.setEnabled(False);self.ports.setEnabled(False)
            self.status.setText('Backing up settings, writing the verified firmware, then checking settings…')
            self.worker=Worker(self.ports.currentData());self.worker.log.connect(self.log.insertPlainText);self.worker.result.connect(self.done_update);self.worker.start()
        def done_update(self,ok,message):
            self.busy=False;self.status.setText(message);self.start.setVisible(not ok);self.start.setEnabled(not ok);self.ports.setEnabled(not ok)
        def closeEvent(self,event):
            if self.busy or (self.worker and self.worker.isRunning()):event.ignore()
            else:super().closeEvent(event)
    window=Window();window.show();result=app.exec();lock.unlock();return result
