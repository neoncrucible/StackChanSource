"""Real Qt/private-process smoke checks; no hardware or provider credentials."""
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
import unittest

import pytest
pytest.importorskip('PySide6.QtWidgets')
from PySide6.QtCore import QLockFile, QProcess
from PySide6.QtWidgets import QApplication, QLineEdit
from kcore.desktop_ui import MainWindow
from kcore.desktop_process import ControlProcess
from kcore.credential_vault import CredentialVault


def pump_until(predicate, seconds=12):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        QApplication.processEvents(); time.sleep(.01)
    assert predicate(), 'Qt condition did not settle'


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.qt=QApplication.instance() or QApplication([])

    def test_real_worker_timezone_project_refresh_privacy_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            prior=os.environ.get('KADENCE_DATA_DIR'); os.environ['KADENCE_DATA_DIR']=tmp
            path=Path(tmp)
            (path/'desktop-settings.json').write_text(json.dumps({'timezone':'Pacific/Auckland'}))
            window=MainWindow(directory=path,load_credentials=False)
            events=[]; window.control.event.connect(lambda n,d:events.append((n,d)))
            try:
                window.show(); window.control.start()
                pump_until(lambda:window.active_timezone=='Pacific/Auckland')
                self.assertTrue(window.start_button.isEnabled())
                window.control.send('project_add',{'name':'Bench fixture'})
                pump_until(lambda:window.entry_table.rowCount()==0 and bool(window.projects))
                pump_until(lambda:not window.control.pending)
                before=len(events)
                deadline=time.monotonic()+.2
                while time.monotonic()<deadline: QApplication.processEvents(); time.sleep(.01)
                self.assertEqual(len(events),before,'read/refresh feedback loop')
                fake='FAKE_ONLY_do_not_store_123'
                for edit in window.secret_fields.values():
                    edit.setText(fake)
                    self.assertEqual(edit.echoMode(),QLineEdit.Password)
                window.save_preferences()
                self.assertNotIn(fake,window.settings_path.read_text())
                window.record_diagnostic('device',{'state':fake,'connected':True,'password':fake,'qr':fake})
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                for index in range(6):
                    window.navigate(index); QApplication.processEvents()
                    self.assertFalse(window.grab().isNull())
                self.assertFalse(window.timezone.isReadOnly())
                window.on_event('server',{'state':'running'})
                self.assertFalse(window.timezone.isEnabled())
                lock=QLockFile(str(path/'fixture.lock')); self.assertTrue(lock.tryLock(0))
                second=QLockFile(str(path/'fixture.lock')); self.assertFalse(second.tryLock(0)); lock.unlock()
                exited=[]; window.control.exited.connect(lambda:exited.append(True))
                window.control.shutdown(); pump_until(lambda:bool(exited))
                self.assertIn(('closed',{'clean':True}),events)
                self.assertFalse(window.control.ready)
            finally:
                window.control.shutdown()
                pump_until(lambda:window.control.process.state()==QProcess.NotRunning)
                window.tray.hide(); window.hide(); window.deleteLater(); QApplication.processEvents()
                if prior is None: os.environ.pop('KADENCE_DATA_DIR',None)
                else: os.environ['KADENCE_DATA_DIR']=prior

    @unittest.skipUnless(os.name=='nt','Windows Credential Manager integration')
    def test_windows_vault_uses_only_its_own_fake_entry(self):
        vault=CredentialVault('Kadence/Test/'+uuid.uuid4().hex)
        fake={'openai_api_key':'fake-openai','gemini_api_key':'fake-gemini','wifi_password':'fake-wifi'}
        try:
            self.assertEqual(vault.load(),{})
            vault.save(fake); self.assertEqual(vault.load(),fake)
            vault.forget(); self.assertEqual(vault.load(),{})
        finally: vault.forget()
