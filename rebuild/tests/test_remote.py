"""Real paired WebSocket sessions, long PTT, shared speech and failure isolation."""
import asyncio
import hashlib
import hmac
import json
import struct
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,patch
import pytest
from websockets.asyncio.client import connect
from kcore.remote_audio import Capture,FRAME_BYTES,remote_turn
from kcore.remote_server import RemoteServer
from kcore.voice_wire import VoiceWireResult


def controller(root):
    events=[];moves=[];spoken=[]
    body=NS(connected=True,send_presentation_state=AsyncMock())
    app=NS(_body=body,_voice_task=None,_companion=NS(abort_turn=lambda:None,commit_spoken=lambda *a:spoken.append(a)),
        _provider_stage=None,_turn_sequence=0,_capture_in_voice=None,_alert_pcm=b'',
        emit=lambda n,d:events.append((n,d)),_report_issue=lambda *a:None,
        tracking=NS(stop=AsyncMock()),motion=NS(stop=AsyncMock()),perception=None,
        _windows_audio=NS(start=lambda pcm:None,finish=AsyncMock(),stop=lambda:None),
        settings=NS(providers=NS(missing_credentials=lambda:[]),audio_output='windows',lan_host='127.0.0.1'),
        camera=NS(config=NS(privacy=False,source='auto'),unitv2=NS(status={'state':'IDLE'})))
    def done(task):
        if app._voice_task is task:app._voice_task=None
        if not task.cancelled():task.result()
    app._voice_task_done=done
    c=NS(app=app,emit=app.emit,services=NS(paths=NS(root=root)),_media=None,camera_voice=AsyncMock(return_value={'spoken':'Applied','ok':True}))
    return c,events,spoken


async def paired(server):
    ws=await connect(f'ws://127.0.0.1:{server.port}/kadence/v1',proxy=None)
    challenge=json.loads(await ws.recv())
    device=server.pairing['device_id']
    proof=hmac.new(bytes.fromhex(server.pairing['key']),f"1:{challenge['nonce']}:{device}".encode(),hashlib.sha256).hexdigest()
    await ws.send(json.dumps({'v':1,'type':'remote.hello','device':'StickS3','device_id':device,'proof':proof}))
    assert json.loads(await ws.recv())['type']=='remote.accept'
    assert json.loads(await ws.recv())['robot_link']=='tethered'
    return ws


async def result(ws,seq):
    while True:
        value=json.loads(await asyncio.wait_for(ws.recv(),3))
        if value.get('type')=='remote.result' and value['seq']==seq:return value


def test_disk_capture_accepts_sixty_seconds_and_uses_bounded_stt_chunks():
    async def case():
        now=[100.];c=Capture(9,clock=lambda:now[0])
        for i in range(1500):
            now[0]+=.04;c.frame(struct.pack('!II',9,i)+bytes(FRAME_BYTES))
        assert c.samples/16000==60 and not c.ready.done()
        c.finish(9,1500)
        calls=[]
        async def transcribe(data,**kwargs):calls.append(len(data));return 'first' if len(calls)==1 else 'second'
        assert await c.transcribe(NS(transcribe_file=transcribe))=='first second'
        assert len(calls)==2 and max(calls)<1000000
        c.close()
    asyncio.run(case())


def test_capture_rejects_sequence_flood_and_incomplete_release():
    async def case():
        c=Capture(4,clock=lambda:0)
        with pytest.raises(ValueError):c.frame(struct.pack('!II',4,1)+bytes(FRAME_BYTES))
        for i in range(51):c.frame(struct.pack('!II',4,i)+bytes(FRAME_BYTES))
        with pytest.raises(ValueError):c.frame(struct.pack('!II',4,51)+bytes(FRAME_BYTES))
        with pytest.raises(ValueError):c.finish(4,50)
        c.close()
    asyncio.run(case())


def test_real_remote_ptt_release_calls_common_pipeline_and_keeps_body(tmp_path):
    async def case():
        c,events,spoken=controller(tmp_path);s=RemoteServer(c);s.pairing={'key':'ab'*32,'device_id':'12'*8}
        seen=[]
        async def process(transcribe,**kwargs):
            seen.append(await transcribe(NS(transcribe_file=AsyncMock(return_value='hello'))))
            return VoiceWireResult('hello','reply',b'\0\0'*800)
        with patch('kcore.voice_wire.process_audio_turn',process):
            await s.listen('127.0.0.1',0)
            try:
                async with await paired(s) as ws:
                    await ws.send(json.dumps({'v':1,'seq':1,'type':'audio.start'}));r=await result(ws,1)
                    assert r['ok'];ident=r['capture'];body=c.app._body
                    # Feed >4 seconds with a test clock, not a real-time sleeping test.
                    now=[s.capture.started];s.capture.clock=lambda:now[0]
                    for i in range(125):
                        now[0]+=.04
                        await ws.send(struct.pack('!II',ident,i)+bytes(FRAME_BYTES))
                    assert not seen
                    await ws.send(json.dumps({'v':1,'seq':2,'type':'audio.stop','capture':ident,'frames':125}))
                    assert (await result(ws,2))['ok']
                    await asyncio.wait_for(s.voice,3)
                    assert seen==['hello'] and spoken==[('hello','reply')]
                    assert c.app._body is body and body.connected
            finally:await s.close()
    asyncio.run(case())


@pytest.mark.parametrize('failure',['off','disconnect','watchdog','malformed'])
def test_failed_remote_capture_is_discarded_without_processing_or_body_disconnect(tmp_path,failure):
    async def case():
        c,events,spoken=controller(tmp_path);s=RemoteServer(c);s.pairing={'key':'ab'*32,'device_id':'12'*8}
        process=AsyncMock()
        with patch('kcore.voice_wire.process_audio_turn',process):
            await s.listen('127.0.0.1',0);ws=await paired(s)
            try:
                await ws.send(json.dumps({'v':1,'seq':1,'type':'audio.start'}));assert (await result(ws,1))['ok']
                captured=s.capture
                if failure=='off':await s.close()
                elif failure=='disconnect':await ws.close()
                elif failure=='watchdog':captured.last-=10
                else:await ws.send(b'invalid pcm')
                for _ in range(100):
                    if captured.closed:break
                    await asyncio.sleep(.01)
                assert captured.closed and not process.called and not spoken
                assert c.app._body.connected
            finally:await ws.close();await s.close()
    asyncio.run(case())


def test_authentication_replay_and_second_client_cannot_take_ownership(tmp_path):
    async def case():
        c,_,_=controller(tmp_path);s=RemoteServer(c);s.pairing={'key':'ab'*32,'device_id':'12'*8}
        await s.listen('127.0.0.1',0)
        try:
            ws=await connect(f'ws://127.0.0.1:{s.port}/kadence/v1',proxy=None)
            await ws.recv();await ws.send(json.dumps({'v':1,'type':'remote.hello','device':'StickS3','device_id':'12'*8,'proof':'00'*32}))
            await ws.wait_closed();assert s.peer is None
            first=await paired(s)
            second=await connect(f'ws://127.0.0.1:{s.port}/kadence/v1',proxy=None)
            await second.wait_closed();assert s.peer is not None
            await first.send(json.dumps({'v':1,'seq':2,'type':'remote.ping','rssi':-40}))
            await first.wait_closed()
            next_peer=await paired(s);await next_peer.close()
        finally:await s.close()
    asyncio.run(case())


def test_camera_command_uses_existing_authority_and_rejects_unsupported_fields(tmp_path):
    async def case():
        c,_,_=controller(tmp_path);s=RemoteServer(c)
        assert await s.command({'v':1,'seq':1,'type':'camera.set','command':'privacy_on'})=={'message':'Applied'}
        c.camera_voice.assert_awaited_once_with('privacy_on')
        with pytest.raises(ValueError):await s.command({'v':1,'seq':2,'type':'gyro.frame','yaw':999})
        with pytest.raises(ValueError):await s.command({'v':1,'seq':3,'type':'camera.set','command':'shell'})
        c.camera_voice.return_value={'ok':False,'spoken':'Lifecycle check needed'}
        with pytest.raises(RuntimeError):await s.command({'v':1,'seq':4,'type':'camera.set','command':'perception_on'})
    asyncio.run(case())


def test_remote_off_cancels_processing_without_committing_or_serial_reset(tmp_path):
    async def case():
        c,events,spoken=controller(tmp_path);s=RemoteServer(c);s.pairing={'key':'ab'*32,'device_id':'12'*8}
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def slow(*a,**kw):
            entered.set()
            try:await asyncio.Event().wait()
            finally:cancelled.set()
        with patch('kcore.voice_wire.process_audio_turn',slow):
            await s.listen('127.0.0.1',0);ws=await paired(s)
            try:
                await ws.send(json.dumps({'v':1,'seq':1,'type':'audio.start'}));ident=(await result(ws,1))['capture']
                await ws.send(struct.pack('!II',ident,0)+bytes(FRAME_BYTES))
                await ws.send(json.dumps({'v':1,'seq':2,'type':'audio.stop','capture':ident,'frames':1}))
                assert (await result(ws,2))['ok'];await entered.wait()
                await s.close()
                assert cancelled.is_set() and not spoken and c.app._body.connected
            finally:await ws.close();await s.close()
    asyncio.run(case())


def test_motion_and_remote_tabs_share_actual_worker_protocol(tmp_path):
    from kcore.desktop_worker import DesktopController
    async def case():
        events=[];c=DesktopController(lambda n,d:events.append((n,d)),directory=tmp_path)
        await c.start()
        try:
            assert any(n=='motion_status' and not d['saved'] for n,d in events)
            assert not (await c.command('remote_status',{}))['enabled']
            with pytest.raises(RuntimeError):await c.command('remote_config',{'enabled':True,'host':'127.0.0.1'})
            with pytest.raises(RuntimeError):await c.command('motion_home',{})
        finally:await c.close()
    asyncio.run(case())
