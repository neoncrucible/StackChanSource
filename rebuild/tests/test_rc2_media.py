import asyncio
import io
import struct
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from kcore.appliance import KadenceAppliance
from kcore.desktop_worker import settings_from_control
from kcore.device_control import request_device
from kcore.host import VoiceTurnFailure
from kcore.protocol import Envelope, MessageKind
from kcore.services import LocalServices
from kcore.vision import IMAGE_BYTES, DeskVision, decode_image, read_image


def settings():
    return settings_from_control({'port':'COM4','ssid':'Test lab','lan_host':'192.168.1.2'})


class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_camera_transfer_requires_current_token_and_bounded_image(self):
        app=KadenceAppliance(settings()); app._body=SimpleNamespace(connected=True)
        app._media_mode='camera'; app._turn_token='a'*32
        server=await asyncio.start_server(app._handle_voice_connection,'127.0.0.1',0)
        port=server.sockets[0].getsockname()[1]
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',port)
            writer.write(b'KDC1'+b'b'*32); await writer.drain()
            self.assertEqual((await reader.read(1024))[:4],b'KDE1')
            writer.close(); await writer.wait_closed(); await asyncio.sleep(0)
            self.assertFalse(app._wire_claimed)
            reader,writer=await asyncio.open_connection('127.0.0.1',port)
            frame=b'\xf8\x00'*(320*240)
            writer.write(b'KDC1'+b'a'*32+b'KDI1'+struct.pack('!HHI',320,240,len(frame))+frame)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(4),2),b'KDAK')
            self.assertEqual(app._media_result,frame)
            writer.close(); await writer.wait_closed()
        finally:
            server.close(); await server.wait_closed(); await app._close_connections()

    async def test_oversized_or_truncated_frame_is_rejected(self):
        for frame,error in [(b'KDI1'+struct.pack('!HHI',320,240,IMAGE_BYTES+2),ValueError),
                            (b'KDI1'+struct.pack('!HHI',320,240,IMAGE_BYTES)+b'x',asyncio.IncompleteReadError),
                            (b'KDI0',RuntimeError)]:
            reader=asyncio.StreamReader(); reader.feed_data(frame); reader.feed_eof()
            with self.assertRaises(error): await read_image(reader)

    async def test_alert_transfers_prepared_audio_without_a_microphone(self):
        app=KadenceAppliance(settings()); app._body=SimpleNamespace(connected=True)
        app._media_mode='alert'; app._turn_token='a'*32; app._alert_pcm=b'\1\0'*400
        server=await asyncio.start_server(app._handle_voice_connection,'127.0.0.1',0)
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            writer.write(b'KDA1'+b'a'*32); await writer.drain()
            result=await asyncio.wait_for(reader.readexactly(808),2)
            self.assertEqual(result,b'KDR1'+struct.pack('!I',800)+app._alert_pcm)
            self.assertTrue(app._media_result)
            writer.close(); await writer.wait_closed()
        finally:
            server.close(); await server.wait_closed(); await app._close_connections()

    async def test_unknown_alert_outcome_is_visible_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            events=[]; service=LocalServices(Path(tmp)); await service.start()
            try:
                await service.reminders.create('check the print','in 20 minutes')
                await service.store.call('claim_due',now=10**12)
                app=KadenceAppliance(settings(),services=service,emit=lambda n,d:events.append((n,d)))
                app._run_media=AsyncMock(side_effect=TimeoutError())
                with patch('kcore.appliance._synthesize_reply',AsyncMock(side_effect=OSError())):
                    await app._deliver_reminders(None)
                    await app._deliver_reminders(None)
                self.assertEqual(app._run_media.await_count,1)
                record=(await service.store.call('reminder_list'))[0]
                self.assertEqual((record['state'],record['robot']),('due','attempted'))
                self.assertIn(('alert',{'state':'review_in_windows','count':1}),events)
            finally: await service.close()

    async def test_camera_rejects_busy_voice_or_game(self):
        app=KadenceAppliance(settings()); app._body=SimpleNamespace(connected=True)
        app._voice_task=asyncio.create_task(asyncio.Event().wait())
        try:
            with self.assertRaises(RuntimeError): await app.capture_snapshot()
        finally:
            app._voice_task.cancel()
            await asyncio.gather(app._voice_task,return_exceptions=True)
        app._voice_task=None; app._last_device_status={'game':'input'}
        with self.assertRaises(RuntimeError): await app.capture_snapshot()


class FakeHost:
    def __init__(self):
        self._command_lock=asyncio.Lock(); self._pending={}; self._active_writer=object()
        self._active_session=SimpleNamespace(hello_seen=True); self.retired=[]
        self.payload={'ok':True}; self.reply=True
    async def _send(self,writer,command):
        if self.reply:
            self._pending[command.request_id].set_result(Envelope(MessageKind.ACK,command.name,self.payload,request_id=command.request_id))
    def _retire_request(self,ident): self.retired.append(ident)


class ControlContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_media_ack_needs_physical_proof_and_retirement(self):
        host=FakeHost()
        payload={'ssid':'Test','password':'','host':'192.168.1.2','port':1,'capture_ms':4800,'token':'a'*32}
        with self.assertRaises(VoiceTurnFailure): await request_device(host,'camera.snapshot',payload)
        host.payload={key:True for key in ('ok','network','capture','handoff','torque_released')}
        self.assertTrue((await request_device(host,'camera.snapshot',payload)).payload['capture'])
        host.reply=False
        with self.assertRaises(TimeoutError): await request_device(host,'device.status',timeout=.01)
        self.assertEqual(len(host.retired),1); self.assertEqual(host._pending,{})
        with self.assertRaises(ValueError): await request_device(host,'device.settings',{'volume':True})
        with self.assertRaises(ValueError): await request_device(host,'device.settings',{'brightness':100})


class VisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rgb565_and_explicit_project_retention(self):
        try: from PIL import Image
        except ImportError: self.skipTest('vision extra not installed')
        png,qr=await asyncio.to_thread(decode_image,b'\xf8\x00'*320*240)
        image=Image.open(io.BytesIO(png))
        self.assertEqual(image.getpixel((10,10)),(255,0,0)); self.assertEqual(qr,[])
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp); service=LocalServices(directory); await service.start()
            try:
                vision=DeskVision(); vision.png=png; vision.captured=1000
                self.assertFalse((directory/'observations').exists())
                with self.assertRaises(ValueError): await vision.save(directory,service.store,99)
                project=await service.store.call('project_add',name='Camera bench')
                await vision.save(directory,service.store,project['id'])
                self.assertEqual(len(list((directory/'observations').glob('*.png'))),1)
                record=(await service.store.call('entry_list',project_id=project['id']))[0]
                self.assertIn('UTC',record['text'])
                vision.clear(); self.assertIsNone(vision.png)
                self.assertEqual(len(list((directory/'observations').glob('*.png'))),1)
            finally: await service.close()
