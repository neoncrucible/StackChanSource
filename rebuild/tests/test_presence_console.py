"""Console navigation, acknowledged controls and shared service behaviour."""
import asyncio
from dataclasses import asdict, replace
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from kcore.camera_manager import CameraConfig
from kcore.desktop_ui import MainWindow
from kcore.desktop_worker import DesktopController


@pytest.fixture
def window(tmp_path):
    qt = QApplication.instance() or QApplication([])
    view = MainWindow(directory=tmp_path, load_credentials=False)
    view.show(); qt.processEvents()
    yield view
    view.ticker.stop(); view.avatar.timer.stop(); view.tray.hide()
    view.quitting=True; view.close(); view.deleteLater(); qt.processEvents()


def test_everyday_pages_and_single_control_locations(window):
    assert [b.text() for b in window.nav] == ['Home','Activity','Tools','Settings']
    assert window.camera_policy.isVisible() and window.camera_privacy.isVisible()
    assert not window.engineering.isVisible()
    assert not window.secret_fields['wifi_password'].isVisible()
    window.navigate(1); QApplication.processEvents()
    assert window.camera_privacy.isVisible()
    assert window.reflex_log.isVisible()
    window.navigate(2); QApplication.processEvents()
    assert window.camera_privacy.isVisible()
    assert window.reminder_table.isVisible()
    window.tools_tabs.setCurrentIndex(3); QApplication.processEvents()
    assert window.tracking_panel.isVisible()
    window.show_engineering('Motion'); QApplication.processEvents()
    assert window.motion_panel.isVisible()
    window.show_engineering('Connection & services'); QApplication.processEvents()
    assert window.secret_fields['wifi_password'].isVisible()
    window.show_profiles(); QApplication.processEvents()
    assert window.profiles_table.isVisible()


@pytest.mark.parametrize('mode', ['OFF','EVENT_ONLY','AWARE'])
def test_awareness_waits_for_ack_and_only_patches_its_own_fields(window, mode):
    saved = CameraConfig(source='robot-camera')
    window.control.ready=True
    window.on_event('camera_settings',asdict(saved))
    with patch.object(window.control,'send',return_value=1) as send:
        window.camera_policy.setCurrentIndex(window.camera_policy.findData(mode))
        window.camera_policy.activated.emit(window.camera_policy.currentIndex())
        action, args, completed = send.call_args.args
        assert action == 'camera_patch'
        assert args == {'policy':mode,'perception_enabled':mode!='OFF'}
        assert window.camera_policy.currentData() == 'OFF'
        assert not window.camera_policy.isEnabled() and window.camera_privacy.isEnabled()
        window.on_event('camera_settings',asdict(replace(saved,**args)))
        completed({'ok':True,'result':{'message':'Camera policy saved.'}})
        assert window.camera_policy.currentData() == mode
        assert window.camera_policy.isEnabled()


def test_refused_awareness_keeps_saved_state_and_explains_gate(window):
    window.control.ready=True
    window.on_event('camera_settings',asdict(CameraConfig()))
    with patch.object(window.control,'send',return_value=1) as send:
        window.camera_policy.setCurrentIndex(2); window.change_awareness()
        send.call_args.args[2]({'ok':False,'message':'Run TEST START / STOP successfully first.'})
    assert window.camera_policy.currentData() == 'OFF'
    assert 'TEST START / STOP' in window.awareness_feedback.text()
    assert window.camera_policy.isEnabled()


def test_privacy_remains_available_during_voice_and_pending_awareness(window):
    window.control.ready=True
    saved=CameraConfig(source='robot-camera')
    window.on_event('camera_settings',asdict(saved))
    window.on_event('server',{'state':'running'})
    window.on_event('activity',{'state':'listening'})
    assert not window.look_button.isEnabled()
    window.unitv2_address.setText('invalid unfinished edit')
    with patch.object(window.control,'send',return_value=1) as send:
        window.camera_policy.setCurrentIndex(2); window.change_awareness()
        assert window.camera_privacy.isEnabled()
        window.camera_privacy.click()
        assert send.call_args.args[:2] == ('camera_patch',{'privacy':True})
        window.on_event('camera_settings',asdict(replace(saved,privacy=True)))
        send.call_args.args[2]({'ok':True})
    assert window.camera_privacy.isChecked()
    assert not window.look_button.isEnabled()
    assert 'privacy' not in window.camera_policy_values()
    assert 'policy' not in window.camera_policy_values()


def test_offline_controls_restart_truth_and_snapshot_gating(window):
    assert not window.camera_policy.isEnabled() and not window.camera_privacy.isEnabled()
    window.control.ready=True
    # A legacy stored policy alone must not claim automatic perception is on.
    saved=CameraConfig(source='robot-camera',policy='AWARE',perception_enabled=False)
    window.on_event('camera_settings',asdict(saved))
    assert window.camera_policy.currentData() == 'OFF'
    window.on_event('server',{'state':'running'})
    assert window.look_button.isEnabled() and not window.describe_button.isEnabled()
    window.on_event('server',{'state':'stopped'})
    assert not window.look_button.isEnabled()
    assert 'unavailable' in window.perception_state.text()
    # The local service can still persist privacy while the robot server is stopped.
    assert window.camera_privacy.isEnabled()
    window.control.ready=False
    window.on_event('fatal',{'message':'Local service unavailable.'})
    assert not window.camera_policy.isEnabled() and not window.camera_privacy.isEnabled()


def test_service_restart_and_voice_use_same_persisted_policy(tmp_path):
    async def case():
        worker=DesktopController(lambda *args:None,directory=tmp_path)
        await worker.start()
        await worker.command('camera_patch',{'source':'robot-camera'})
        await worker.camera_voice('aware')
        await worker.command('camera_patch',{'privacy':True})
        await worker.command('camera_patch',{'greetings':True})
        await worker.close()
        events=[]
        reopened=DesktopController(lambda name,data:events.append((name,data)),directory=tmp_path)
        await reopened.start()
        settings=next(data for name,data in events if name=='camera_settings')
        assert settings['policy']=='AWARE' and settings['perception_enabled'] and settings['privacy'] and settings['greetings']
        await reopened.camera_voice('perception_off')
        assert not CameraConfig.load(tmp_path).perception_enabled
        assert CameraConfig.load(tmp_path).privacy
        await reopened.close()
    asyncio.run(case())


def test_unsent_request_cannot_leave_control_pending(window):
    window.control.ready=True
    window.on_event('camera_settings',asdict(CameraConfig()))
    with patch.object(window.control,'send',return_value=None):
        window.camera_privacy.click()
    assert not window.camera_privacy.isChecked()
    assert window.camera_privacy.isEnabled() and not window._camera_pending
    assert 'not sent' in window.awareness_feedback.text()


def test_failed_worker_write_reports_unsent_and_releases_pending(window):
    from PySide6.QtCore import QProcess
    from types import SimpleNamespace
    control=window.control; control.ready=True
    with patch.object(control,'process',SimpleNamespace(state=lambda:QProcess.Running,write=lambda raw:-1)):
        assert control.send('camera_patch',{'privacy':True}) is None
    assert not control.pending


def test_unsent_look_releases_ui_and_voice_can_still_preempt(window):
    window.control.ready=True
    window.on_event('camera_settings',asdict(CameraConfig(source='robot-camera')))
    window.on_event('server',{'state':'running'})
    with patch.object(window.control,'send',return_value=None): window.look_camera()
    assert not window._look_pending and window.look_button.isEnabled()
    with patch.object(window.control,'send',return_value=1) as send:
        window.look_camera()
        completed=send.call_args.args[2]
        window.on_event('activity',{'state':'listening'})
        completed({'ok':False,'message':'Interrupted by voice.'})
    assert not window.look_button.isEnabled() and window.camera_privacy.isEnabled()
