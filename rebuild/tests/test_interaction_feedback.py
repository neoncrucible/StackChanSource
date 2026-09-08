import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from kcore.appliance import KadenceAppliance
from kcore.config import RuntimeConfig
from kcore.desktop_worker import settings_from_control
from kcore.host import HostServer, Session
from kcore.protocol import Envelope, MessageKind


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    def app(self):
        self.events=[]
        return KadenceAppliance(settings_from_control({"port":"COM4","ssid":"Test","lan_host":"192.168.1.2"}),
                               emit=lambda name,data:self.events.append((name,data)))

    async def test_touch_does_not_claim_recording_before_the_device_opens_mic(self):
        app=self.app()
        app._run_voice_turn=AsyncMock()
        app._begin_voice_turn(object(),Envelope(MessageKind.EVENT,"voice.request",{"trigger":"touch"}))
        self.assertEqual(self.events,[("activity",{"state":"attentive"})])
        await app._voice_task
        await asyncio.sleep(0)

    async def test_recording_and_playback_phases_must_match_a_live_command(self):
        app=self.app()
        body=SimpleNamespace(host=SimpleNamespace(_pending={"current":object()}))
        app._body=body; app._turn_token="a"*32
        def phase(state="listening",ident="current",duration=4800):
            return Envelope(MessageKind.EVENT,"voice.phase",{"request_id":ident,"state":state,"capture_ms":duration})
        app._handle_voice_phase(body,phase(ident="retired"))
        app._handle_voice_phase(body,phase(duration=True))
        app._handle_voice_phase(body,phase(state="PRIVATE_TEXT"))
        self.assertEqual(self.events,[])
        app._handle_voice_phase(body,phase())
        app._handle_voice_phase(body,phase("thinking"))
        app._handle_voice_phase(body,phase("speaking"))
        self.assertEqual(self.events,[("activity",{"state":"listening","capture_ms":4800}),
                                     ("activity",{"state":"thinking"}),("activity",{"state":"speaking"})])
        body.host._pending.clear()
        app._handle_voice_phase(body,phase())
        self.assertEqual(len(self.events),3)
        body.host._pending["current"]=object(); app._turn_token=None
        app._handle_voice_phase(body,phase())
        self.assertEqual(len(self.events),3)

    async def test_cancel_confirmation_retires_missing_final_voice_ack(self):
        app=self.app()
        app._server_port=12345
        host=HostServer(RuntimeConfig("127.0.0.1",0,5,15))
        host._active_writer=object(); host._active_session=Session("test",True)
        sent=asyncio.Event(); commands=[]
        async def send(writer,command):
            commands.append(command); sent.set() # Deliberately lose the final voice ACK.
        host._send=send
        body=SimpleNamespace(host=host,send_voice_turn=host.send_voice_turn,
            send_voice_cancel=AsyncMock(return_value=Envelope(MessageKind.ACK,"voice.cancel",{"ok":True,"torque_released":True})))
        app._body=body
        turn=asyncio.create_task(app._run_voice_turn(body)); app._voice_task=turn
        await asyncio.wait_for(sent.wait(),1)
        await asyncio.wait_for(app._handle_touch_cancel(body,Envelope(MessageKind.EVENT,"voice.touch-cancel",{"trigger":"touch"})),1)
        self.assertTrue(turn.done())
        self.assertIsNone(app._voice_task)
        self.assertFalse(host._command_lock.locked())
        self.assertEqual(host._pending,{})
        self.assertIn(commands[0].request_id,host._retired)
        host._resolve_pending(Envelope(MessageKind.ACK,"voice.turn",{"ok":False},request_id=commands[0].request_id))
        self.assertEqual(host._pending,{})
