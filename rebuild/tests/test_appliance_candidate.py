"""Exercise the normal appliance over real loopback TCP with a simulated device.

External voice adapters and physical I/O are substituted; the wire, coordinator,
tool authority, SQLite, cancellation and confirmation lifecycle run for real.
"""
from __future__ import annotations

import asyncio
import contextlib
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kcore.appliance import ApplianceSettings, KadenceAppliance
from kcore.companion import Companion
from kcore.context_store import ContextStore
from kcore.local_tools import make_local_tools
from kcore.protocol import Envelope, MessageKind
from kcore.runtime import RuntimeBody
from kcore.config import RuntimeConfig
from kcore.voice_providers import VoiceNoSpeechDetected, VoiceProviderSettings, pcm16_mono_to_wav


class Adapters:
    def __init__(self):
        self.text = "What time is it?"
        self.failure = None
        self.stt = self.thinker = self.tts = self
        self.entered = asyncio.Event()
        self.hang = False
        self.cancelled = asyncio.Event()
        self.response = '{"reply":"Hello there."}'

    async def transcribe_file(self, *args, **kwargs):
        self.entered.set()
        if self.hang:
            try: await asyncio.Event().wait()
            finally: self.cancelled.set()
        if self.failure: raise self.failure
        return self.text

    async def stream_reply(self, text):
        yield self.response

    async def synthesize(self, text):
        # Real miniaudio decoder consumes a tiny valid audio container.
        yield pcm16_mono_to_wav(b"\0\0" * 160, 16000)


class Device:
    connected = True

    def __init__(self, app):
        self.app = app
        self.states = []
        self.played = 0
        self.moved = 0
        self.fail_playback = False
        self.cancel_calls = 0

    async def send_presentation_state(self, state, **kwargs):
        self.states.append(state)

    async def send_body_pose(self, yaw, pitch, **kwargs):
        self.moved += 1
        return Envelope(MessageKind.ACK, "body.pose", {"executed": True, "torque_released": True})

    async def send_voice_cancel(self, **kwargs):
        self.cancel_calls += 1
        return Envelope(MessageKind.ACK, "voice.cancel", {"ok": True, "torque_released": True})

    async def send_voice_turn(self, *, token, **kwargs):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.app._server_port)
        try:
            writer.write(struct.pack("!4sHH", b"KDV2", 16000, 60) + token.encode() + b"\0\3abc\0\0")
            await writer.drain()
            magic = await reader.readexactly(4)
            if magic != b"KDR1": raise RuntimeError("device received a contained service failure")
            size = struct.unpack("!I", await reader.readexactly(4))[0]
            pcm = await reader.readexactly(size)
            if self.fail_playback: raise RuntimeError("device playback failed")
            self.played += len(pcm)
            return Envelope(MessageKind.ACK, "voice.turn", {"ok": True})
        finally:
            writer.close()
            with contextlib.suppress(Exception): await writer.wait_closed()

    async def wait_disconnected(self): await asyncio.Event().wait()
    async def next_event(self): await asyncio.Event().wait()
    async def close(self): self.connected = False


class ApplianceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ContextStore(Path(self.temp.name))
        await self.store.start()
        settings = ApplianceSettings("COM4",115200,4800,0.01,"test","test","127.0.0.1",VoiceProviderSettings("test","test"))
        self.app = KadenceAppliance(settings)
        self.app._companion = Companion(make_local_tools(self.store),self.store)
        self.device = Device(self.app)
        self.app._body = self.device
        self.adapters = Adapters()
        self.mock = patch("kcore.voice_wire.LiveVoiceProviders.from_settings", return_value=self.adapters)
        self.mock.start()
        await self.app._start_voice_server()

    async def asyncTearDown(self):
        await self.app.close()
        self.mock.stop()
        self.temp.cleanup()

    async def turn(self):
        self.app._voice_task = asyncio.create_task(self.app._run_voice_turn(self.device))
        await asyncio.wait_for(self.app._voice_task, 2)
        await asyncio.sleep(0)

    async def test_repeated_normal_turns_and_device_ack_commit(self):
        await self.turn()
        await self.turn()
        self.assertGreater(self.device.played,0)
        self.assertEqual(self.device.moved,2)
        self.assertEqual(len(self.app._companion.history),2)
        self.assertIn("tool-working",self.device.states)
        self.assertEqual(self.app._connections,{})
        self.assertIsNone(self.app._provider_task)

    async def test_unheard_confirmation_is_not_authoritative(self):
        self.adapters.text = "Please keep the detail we discussed"
        self.adapters.response = '{"tool":"remember","arguments":{"text":"the marker is violet"}}'
        self.device.fail_playback = True
        await self.turn()
        self.device.fail_playback = False
        self.adapters.text = "Yes"
        await self.turn()
        self.assertEqual((await self.store.perform("list"))["items"],[])
        self.assertEqual(len(self.app._companion.history),1)

    async def test_provider_failure_and_no_speech_recover_next_turn(self):
        self.adapters.failure = RuntimeError("external provider failed")
        await self.turn()
        self.assertEqual(len(self.app._companion.history),0)
        self.adapters.failure = VoiceNoSpeechDetected()
        await self.turn()
        self.assertGreater(self.device.played,0)
        self.assertEqual(len(self.app._companion.history),0)
        self.adapters.failure = None
        await self.turn()
        self.assertEqual(len(self.app._companion.history),1)

    async def test_touch_cancel_cancels_provider_and_releases_connection(self):
        self.adapters.hang = True
        self.app._voice_task = asyncio.create_task(self.app._run_voice_turn(self.device))
        turn = self.app._voice_task
        await asyncio.wait_for(self.adapters.entered.wait(),1)
        await self.app._handle_touch_cancel(self.device, Envelope(MessageKind.EVENT,"voice.touch-cancel",{"trigger":"touch"}))
        await asyncio.wait_for(self.adapters.cancelled.wait(),1)
        await asyncio.wait_for(asyncio.gather(turn,return_exceptions=True),1)
        self.assertEqual(len(self.app._companion.history),0)
        self.assertIsNone(self.app._turn_token)
        self.adapters.hang = False
        await self.turn()
        self.assertEqual(len(self.app._companion.history),1)

    async def test_idle_lan_connection_never_reaches_providers(self):
        reader,writer=await asyncio.open_connection("127.0.0.1",self.app._server_port)
        self.assertEqual(await asyncio.wait_for(reader.read(),1),b"")
        self.assertFalse(self.adapters.entered.is_set())
        writer.close()
        await writer.wait_closed()

    async def test_connected_supervisor_cancel_has_no_orphan_tasks(self):
        task=asyncio.create_task(self.app._run_connected(self.device))
        await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        names={t.get_name() for t in asyncio.all_tasks() if not t.done()}
        self.assertNotIn("kadence-device-events",names)
        self.assertNotIn("kadence-device-disconnect",names)

    async def test_disconnect_replacement_uses_new_session(self):
        await self.turn()
        old=self.device
        await old.close()
        self.device=Device(self.app)
        self.app._body=self.device
        await self.turn()
        self.assertEqual(self.device.moved,1)
        self.assertEqual(len(self.app._companion.history),2)

    async def test_cancel_during_serial_start_closes_port(self):
        class WaitingSerial:
            def __init__(self):
                self.started=threading.Event()
                self.closed=threading.Event()
            def readline(self):
                self.started.set()
                self.closed.wait(.5)
                return b""
            def close(self): self.closed.set()
        port=WaitingSerial()
        task=asyncio.create_task(RuntimeBody.open(RuntimeConfig("127.0.0.1",8765,5,15),serial_factory=lambda *a,**kw:port))
        while not port.started.is_set(): await asyncio.sleep(.005)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(port.closed.is_set())


if __name__ == "__main__": unittest.main()
