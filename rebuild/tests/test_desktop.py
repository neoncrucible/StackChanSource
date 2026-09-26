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
                window.camera_source.setCurrentIndex(1)
                window.unitv2_address.setText('192.168.40.175')
                self.assertTrue(window.unitv2_address.isEnabled())
                from unittest.mock import patch
                with patch.object(window.control, 'send') as send:
                    window.capture_camera()
                    self.assertEqual(send.call_args.args[0],'camera_settings')
                    callback=send.call_args.args[2]
                    send.reset_mock()
                    callback({'ok':True})
                    send.assert_called_once_with('camera_capture', {'source':'unitv2-camera', 'address':'192.168.40.175'})
                window.save_preferences()
                preferences=json.loads(window.settings_path.read_text())
                self.assertEqual(preferences['camera_source'],'unitv2-camera')
                self.assertEqual(preferences['unitv2_address'],'192.168.40.175')
                self.assertNotIn(fake,window.settings_path.read_text())
                self.assertEqual(window.ollama_model.currentText(),'qwen3.5:4b')
                with patch.object(window.control, 'send') as send:
                    window.refresh_models()
                    callback=send.call_args.args[2]
                    callback({'ok':True,'result':{'models':['qwen3.5:4b','custom:latest']}})
                self.assertGreaterEqual(window.ollama_model.findText('custom:latest'),0)
                self.assertEqual(window.ollama_model.currentText(),'qwen3.5:4b')
                window.ollama_model.setCurrentText('custom:latest')
                window.save_settings()
                self.assertEqual(json.loads(window.settings_path.read_text())['ollama_model'],'custom:latest')
                window.ollama_model.setCurrentText('qwen3.5:4b')
                window._load_settings(False)
                self.assertEqual(window.ollama_model.currentText(),'custom:latest')
                with patch.object(window.control, 'send') as send:
                    window.refresh_models()
                    send.call_args.args[2]({'ok':False,'message':'Ollama unavailable'})
                self.assertEqual(window.ollama_model.currentText(),'custom:latest')
                self.assertTrue(window.models_refresh.isEnabled())
                with patch.object(window.control, 'send') as send:
                    window.test_ollama_reply()
                    self.assertEqual(send.call_args.args[:2], ('ollama_reply_check', {'model':'custom:latest'}))
                    self.assertFalse(window.reply_check.isEnabled())
                    send.call_args.args[2]({'ok':True,'result':{'passed':True,'message':'Valid reply'}})
                self.assertTrue(window.reply_check.isEnabled())
                self.assertEqual(window.message.text(),'Valid reply')
                window.on_event('runtime_issue',{'stage':'providers','provider_stage':'reasoning',
                    'provider':'ollama','reason':'invalid_plan','reply':fake,'error':fake})
                self.assertIn('reply format',window.message.text())
                self.assertEqual(window.diagnostic[-1]['reason'],'invalid_plan')
                self.assertEqual(window.diagnostic[-1]['provider'],'ollama')
                window.on_event('runtime_issue',{'stage':'providers','provider_stage':'reasoning',
                    'provider':'ollama','reason':'model_error','http_status':500,'message':fake})
                self.assertEqual(window.diagnostic[-1]['http_status'],500)
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                window.record_diagnostic('runtime_issue',{'provider':fake,'http_status':fake,'reason':fake})
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                window.record_diagnostic('device',{'state':fake,'connected':True,'password':fake,'qr':fake})
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                window.record_diagnostic('device_diagnostic',{'reason':'interrupt-watchdog','cpu':1,
                    'backtrace':[0x42012345,0x40371234],'message':fake,'component':fake})
                self.assertEqual(window.diagnostic[-1]['reason'],'interrupt-watchdog')
                self.assertEqual(window.diagnostic[-1]['backtrace'],[0x42012345,0x40371234])
                self.assertNotIn('component',window.diagnostic[-1])
                window.record_diagnostic('camera_transfer',{'stage':'image-data','reason':'interrupted',
                    'received_bytes':123,'expected_bytes':153600,'pixels':fake})
                self.assertEqual(window.diagnostic[-1]['received_bytes'],123)
                self.assertEqual(window.diagnostic[-1]['stage'],'image-data')
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                for index in range(6):
                    window.navigate(index); QApplication.processEvents()
                    self.assertFalse(window.grab().isNull())
                self.assertFalse(window.timezone.isReadOnly())
                window.on_event('server',{'state':'running'})
                self.assertFalse(window.timezone.isEnabled())
                with patch.object(window.control,'send') as send:
                    window.test_ollama_reply()
                    send.assert_not_called()
                    self.assertIn('Stop the server',window.message.text())
                window.on_event('activity',{'state':'listening','capture_ms':4800})
                self.assertIn('LISTENING',window.activity.text())
                self.assertGreater(window.capture_until,time.monotonic())
                window.on_event('activity',{'state':'thinking'})
                self.assertEqual(window.capture_until,0)
                window.on_event('provider_stage',{'stage':'tts'})
                window.tick()
                self.assertIn('PREPARING VOICE',window.activity.text())
                window.on_event('provider_stage',{'stage':'tts_fallback','reply':fake})
                self.assertIn('LOCAL VOICE',window.activity.text())
                self.assertIn('installed Windows voice',window.message.text())
                self.assertEqual(window.diagnostic[-1]['stage'],'tts_fallback')
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                window.record_diagnostic('device',{'presentation':'listening','touch_seq':4,
                    'capture_remaining_ms':4200,'password':fake})
                self.assertEqual(window.diagnostic[-1]['state'],'listening')
                self.assertEqual(window.diagnostic[-1]['touch_seq'],4)
                self.assertNotIn(fake,json.dumps(list(window.diagnostic)))
                # Ambient presentation cannot claim microphone preparation;
                # device polling cannot replace a live host provider phase.
                window.on_event('activity',{'state':'idle'})
                window.on_event('device',{'presentation':'attentive','media_busy':False})
                self.assertEqual(window.activity.text(),'ATTENTIVE')
                window.on_event('activity',{'state':'attentive'})
                self.assertIn('CONNECTING AUDIO',window.activity.text())
                window.on_event('activity',{'state':'thinking'})
                window.on_event('provider_stage',{'stage':'tts'})
                window.on_event('device',{'presentation':'idle','media_busy':False})
                self.assertIn('PREPARING VOICE',window.activity.text())
                window.on_event('voice_recovery',{'state':'reconnecting'})
                self.assertIn('Recovering',window.voice_health.text())
                window.on_event('voice_recovery',{'state':'ready'})
                self.assertIn('Tap',window.voice_health.text())
                window.on_event('vision_description',{'state':'failed','reason':'quota','http_status':429,
                    'source_device':'unitv2-camera','response':fake,'key':fake})
                self.assertIn('quota',window.vision_description_status.text())
                window.on_event('activity',{'state':'idle'})
                with patch.object(window.control,'send') as send:
                    window.look_camera()
                    self.assertEqual(send.call_args.args[0],'camera_settings')
                    self.assertFalse(window.look_button.isEnabled())
                    send.call_args.args[2]({'ok':True})
                    self.assertEqual(send.call_args.args[0],'camera_look')
                    send.call_args.args[2]({'ok':False,'message':'A precise test failure'})
                self.assertTrue(window.look_button.isEnabled())
                self.assertEqual(window.vision_description_status.text(),'A precise test failure')
                for index in range(500):
                    window.record_diagnostic('device',{'touch_seq':index,'password':fake})
                important=list(window.important_diagnostics)
                self.assertTrue(any(e['event']=='vision_description' and e.get('reason')=='quota' for e in important))
                self.assertNotIn(fake,json.dumps(important))
                self.assertLessEqual(len(window.diagnostic),400)
                export=path/'production-diagnostics.json'
                with patch('kcore.desktop_ui.QFileDialog.getSaveFileName',return_value=(str(export),'')):
                    window.export_diagnostics()
                exported=json.loads(export.read_text())
                self.assertEqual(exported['important_events'],important)
                self.assertNotIn(fake,json.dumps(exported))
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
