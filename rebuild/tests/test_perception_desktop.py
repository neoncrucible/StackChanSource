import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kcore.camera_manager import CameraConfig, CameraManager
from kcore.desktop_worker import DesktopController
from kcore.vision import DeskVision


def test_privacy_is_saved_even_with_invalid_address(tmp_path):
    async def case():
        events=[]
        controller=DesktopController(lambda *args:events.append(args),directory=tmp_path)
        await controller.start()
        camera=CameraManager(None)
        controller.app=SimpleNamespace(camera=camera,vision=DeskVision(),perception=None)
        values=asdict(CameraConfig(privacy=True));values['address']='bad address'
        try:
            await controller.command('camera_settings',values)
            assert False
        except ValueError:pass
        assert camera.config.privacy and CameraConfig.load(tmp_path).privacy
        controller.app=None
        await controller.close()
    asyncio.run(case())


def test_worker_config_reopens_and_off_does_not_enable_autonomy(tmp_path):
    async def case():
        controller=DesktopController(lambda *args:None,directory=tmp_path)
        await controller.start()
        await controller.command('camera_settings',asdict(CameraConfig(policy='EVENT_ONLY',privacy=True)))
        await controller.close()
        events=[]
        reopened=DesktopController(lambda *args:events.append(args),directory=tmp_path)
        await reopened.start()
        assert next(data for name,data in events if name=='camera_settings')['privacy'] is True
        await reopened.close()
    asyncio.run(case())


def test_console_controls_and_biometric_status_not_in_diagnostics(tmp_path):
    from PySide6.QtWidgets import QApplication
    from kcore.desktop_ui import MainWindow
    qt=QApplication.instance() or QApplication([])
    window=MainWindow(directory=tmp_path,load_credentials=False)
    try:
        window.on_event('camera_settings',asdict(CameraConfig(policy='AWARE',privacy=True)))
        assert window.camera_policy.currentData()=='AWARE' and window.camera_privacy.isChecked()
        assert window.camera_source.currentData()=='auto'
        with patch.object(window.control,'send') as send:
            window.apply_camera_policy()
            assert send.call_args.args==('camera_settings',asdict(CameraConfig(policy='AWARE',privacy=True)))
        window.on_event('perception',{'occupancy':'OCCUPIED','sensor_health':'ready','health':'ready','model_health':'ready','subjects':2,'confirmed_persons':['private-person']})
        assert 'confirmed 1' in window.perception_state.text()
        window.record_diagnostic('perception',{'confirmed_persons':['private-person'],'embedding':[123],'name':'private-name'})
        assert 'private-person' not in json.dumps(list(window.diagnostic))
        assert 'private-name' not in json.dumps(list(window.diagnostic))
        window.navigate(3)
        window.show();qt.processEvents()
        assert window.camera_policy.isVisible()
    finally:
        window.ticker.stop();window.quitting=True;window.close()
