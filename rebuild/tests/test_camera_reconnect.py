import asyncio
from dataclasses import replace
import json
from unittest.mock import AsyncMock, patch

import pytest

from kcore.camera_faults import CameraFault
from kcore.camera_manager import CameraConfig, CameraManager, decode_jpeg
from kcore.unitv2_lifecycle import LifecycleError


@pytest.mark.parametrize('failure,code',[
    (ConnectionRefusedError('PRIVATE NETWORK RESPONSE'),'connection_refused'),
    (TimeoutError('PRIVATE NETWORK RESPONSE'),'timeout'),
    (LifecycleError('PRIVATE NETWORK RESPONSE',code='pairing_rejected'),'pairing_rejected'),
    (LifecycleError('PRIVATE NETWORK RESPONSE',code='frame_timeout'),'frame_timeout'),
])
def test_voice_camera_failure_keeps_the_real_category_and_can_retry_immediately(failure,code):
    async def case():
        events=[]
        camera=CameraManager(None,emit=lambda *a:events.append(a))
        camera.unitv2.capture=AsyncMock(side_effect=[failure,(b'png',32,24,())])
        with pytest.raises(CameraFault) as error:await camera.acquire(source='unitv2-camera',purpose='voice')
        assert error.value.code==code
        assert 'PRIVATE' not in str(error.value) and 'PRIVATE' not in json.dumps(events)
        assert ('camera_issue',{'code':code,'source':'unitv2-camera'}) in events
        frame=await camera.acquire(source='unitv2-camera',purpose='voice')
        assert frame.source=='unitv2-camera' and camera.failure is None
        assert camera.unitv2.capture.await_count==2
    asyncio.run(case())


def test_late_camera_boot_recovers_automatically_and_repeated_fault_is_not_spammed():
    async def case():
        events=[];pauses=[]
        camera=CameraManager(None,emit=lambda *a:events.append(a),config=CameraConfig(policy='AWARE',perception_enabled=True))
        camera.unitv2.ensure_ready=AsyncMock(side_effect=[ConnectionRefusedError(),ConnectionRefusedError(),None])
        async def pause(seconds):pauses.append(seconds)
        await camera.prepare_automatically(pause=pause)
        assert pauses==[2,5] and camera.unitv2.ensure_ready.await_count==3
        assert camera.failure is None and camera.state=='IDLE'
        assert len([e for e in events if e[0]=='camera_issue'])==1
    asyncio.run(case())


@pytest.mark.parametrize('change',['privacy','address','off','close'])
def test_background_reconnect_stops_when_request_is_revoked(change):
    async def case():
        camera=CameraManager(None,config=CameraConfig(policy='AWARE',perception_enabled=True))
        camera.unitv2.ensure_ready=AsyncMock(side_effect=TimeoutError())
        async def pause(seconds):
            if change=='close': camera._closed=True
            else:
                updates={'privacy':True} if change=='privacy' else {'address':'192.168.40.42'} if change=='address' else {'policy':'OFF'}
                camera.configure(replace(camera.config,**updates))
        await camera.prepare_automatically(pause=pause)
        assert camera.unitv2.ensure_ready.await_count==1
    asyncio.run(case())


def test_unreadable_camera_frame_is_not_reported_as_wifi_failure():
    with pytest.raises(CameraFault) as failure:decode_jpeg(b'not an image')
    assert failure.value.code=='invalid_image'


def test_reconnect_button_uses_existing_service_and_home_keeps_actionable_error(tmp_path):
    from PySide6.QtWidgets import QApplication
    from kcore.desktop_ui import MainWindow
    qt=QApplication.instance() or QApplication([])
    window=MainWindow(directory=tmp_path,load_credentials=False)
    try:
        with patch.object(window.control,'send') as send, patch('kcore.unitv2_setup.launch') as setup:
            window.reconnect_unitv2()
            assert send.call_args.args[0]=='camera_patch'
            callback=send.call_args.args[2];send.reset_mock()
            callback({'ok':True})
            send.assert_called_once_with('unitv2_connect',{},timeout=30)
            setup.assert_not_called()
        window.server_state='running'
        window.on_event('camera_issue',{'code':'frame_timeout','source':'unitv2-camera','raw':'PRIVATE'})
        window.update_controls()
        assert 'no fresh image' in window.home_camera_status.text()
        window.record_diagnostic('camera_issue',{'code':'frame_timeout','source':'unitv2-camera','raw':'PRIVATE'})
        assert 'PRIVATE' not in json.dumps(list(window.diagnostic))
        assert window.diagnostic[-1]['code']=='frame_timeout'
        window.on_event('camera_state',{'state':'IDLE','policy':'AWARE','error_code':None})
        assert 'no fresh image' not in window.home_camera_status.text()
    finally:
        window.ticker.stop();window.quitting=True;window.close();qt.processEvents()
