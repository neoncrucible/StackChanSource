"""Lost device ACKs and failed connections must not strand the voice owner."""
import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from kcore.appliance import ApplianceSettings, KadenceAppliance
from kcore.config import RuntimeConfig
from kcore.host import HostServer, Session, VoiceTurnFailure
from kcore.protocol import Envelope, MessageKind
from kcore.services import LocalServices
from kcore.voice_providers import VoiceProviderSettings
from test_appliance_candidate import Adapters, Device


def settings():
    return ApplianceSettings("COM4",115200,4800,.01,"test","test","127.0.0.1",VoiceProviderSettings("fake","fake"))


class VoiceRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_connection_and_ack_retire_serial_command_without_210_second_wait(self):
        events=[];app=KadenceAppliance(settings(),emit=lambda n,d:events.append((n,d)))
        host=HostServer(RuntimeConfig("127.0.0.1",0,5,15))
        host._active_writer=object();host._active_session=Session("test",True)
        commands=[]
        async def send(writer,command):commands.append(command)
        host._send=send
        body=SimpleNamespace(host=host,connected=True,send_voice_turn=host.send_voice_turn,
            send_voice_cancel=AsyncMock(return_value=Envelope(MessageKind.ACK,"voice.cancel",{"ok":True,"torque_released":True})))
        app._body=body;app._server_port=1234
        with patch("kcore.appliance.VOICE_CONNECT_TIMEOUT",.04):
            await asyncio.wait_for(app._run_voice_turn(body),.5)
        self.assertFalse(host._pending);self.assertFalse(host._command_lock.locked())
        self.assertIn(commands[0].request_id,host._retired)
        self.assertIsNone(app._turn_token);self.assertTrue(app._reconnect_requested.is_set())
        body.send_voice_cancel.assert_awaited_once()
        issues=[d for n,d in events if n=="runtime_issue"]
        self.assertEqual(issues[-1]["voice_stage"],"connecting")
        self.assertEqual(app._turn_sequence,0)
        # Late success proof belongs to the retired command and cannot revive it.
        host._resolve_pending(Envelope(MessageKind.ACK,"voice.turn",{"ok":True},request_id=commands[0].request_id))
        self.assertEqual(app._turn_sequence,0)
        app._body=None;await app.close()

    async def test_tcp_failure_recovers_through_real_supervisor_without_replaying_a_turn(self):
        with tempfile.TemporaryDirectory() as root:
            services=LocalServices(directory=Path(root));await services.start()
            events=[];app=KadenceAppliance(settings(),services=services,emit=lambda n,d:events.append((n,d)))
            first=Device(app);second=Device(app);opened=[];second_ready=asyncio.Event()
            failure=VoiceTurnFailure(["ok"],{"stage":"tcp-connect","error_code":116,"torque_released":True})
            first.send_voice_turn=AsyncMock(side_effect=failure)
            async def open_body(*args,**kwargs):
                item=first if not opened else second;opened.append(item)
                if len(opened)==2:second_ready.set()
                return item
            async def idle_utility():await asyncio.Event().wait()
            adapters=Adapters()
            with patch("kcore.appliance.RuntimeBody.open",side_effect=open_body), \
                 patch.object(app,"_utility_loop",side_effect=idle_utility), \
                 patch("kcore.voice_wire.LiveVoiceProviders.from_settings",return_value=adapters):
                runner=asyncio.create_task(app.run_forever())
                try:
                    async with asyncio.timeout(2):
                        while app._body is not first:await asyncio.sleep(.005)
                    app._begin_voice_turn(first,Envelope(MessageKind.EVENT,"voice.request",{"trigger":"touch"}))
                    await asyncio.wait_for(second_ready.wait(),2)
                    async with asyncio.timeout(2):
                        while app._body is not second:await asyncio.sleep(.005)
                    self.assertFalse(first.connected)
                    self.assertEqual(first.send_voice_turn.await_count,1)
                    self.assertEqual(second.played,0)  # No automatic mic retry or replay.
                    self.assertFalse(app._companion.history)
                    self.assertIn(("voice_recovery",{"state":"ready"}),events)
                    app._begin_voice_turn(second,Envelope(MessageKind.EVENT,"voice.request",{"trigger":"touch"}))
                    await asyncio.wait_for(app._voice_task,2)
                    self.assertGreater(second.played,0)
                    self.assertEqual(len(app._companion.history),1)
                    # A persistent fault cannot create an automatic reset loop.
                    app._recover_voice_connection(second)
                    self.assertFalse(app._reconnect_requested.is_set())
                    self.assertEqual(events[-1],("voice_recovery",{"state":"unavailable","reason":"cooldown"}))
                finally:
                    runner.cancel();await asyncio.gather(runner,return_exceptions=True)
                    await services.close()

    async def test_lost_playback_ack_and_provider_failure_release_host_and_allow_next_turn(self):
        with tempfile.TemporaryDirectory() as root:
            services=LocalServices(directory=Path(root));await services.start()
            app=KadenceAppliance(settings(),services=services);await app._start_companion();await app._start_voice_server()
            adapters=Adapters();device=Device(app);app._body=device
            normal=device.send_voice_turn
            async def lose_ack(**kwargs):
                await normal(**kwargs)
                await asyncio.Event().wait()
            device.send_voice_turn=lose_ack
            original_stage=app._set_voice_stage
            def stage(name,seconds):original_stage(name,.04 if name=="playback" else seconds)
            with patch("kcore.voice_wire.LiveVoiceProviders.from_settings",return_value=adapters),patch.object(app,"_set_voice_stage",side_effect=stage):
                try:
                    await asyncio.wait_for(app._run_voice_turn(device),2)
                    self.assertGreater(device.played,0)
                    self.assertFalse(app._companion.history)
                    self.assertIsNone(app._wire_result);self.assertIsNone(app._turn_token)
                    self.assertFalse(app._connections)
                    app._reconnect_requested.clear();device.send_voice_turn=normal
                    await asyncio.wait_for(app._run_voice_turn(device),2)
                    self.assertEqual(len(app._companion.history),1)
                    # Provider failure with a lost final device ACK retires the
                    # turn immediately, without waiting even for the stage limit.
                    adapters.failure=RuntimeError("private provider response")
                    async def ignore_failure(**kwargs):
                        try:await normal(**kwargs)
                        except RuntimeError:await asyncio.Event().wait()
                    device.send_voice_turn=ignore_failure
                    await asyncio.wait_for(app._run_voice_turn(device),2)
                    self.assertEqual(len(app._companion.history),1)
                    self.assertIsNone(app._turn_token);self.assertFalse(app._connections)
                    self.assertIsNone(app._provider_task)
                finally:await app.close();await services.close()

    async def test_auto_lan_refreshes_before_turn_and_explicit_address_stays_selected(self):
        for auto in (True,False):
            app=KadenceAppliance(replace(settings(),lan_auto=auto))
            cancelled=VoiceTurnFailure(["ok"],{"stage":"cancelled","cancelled":True,"torque_released":True})
            body=SimpleNamespace(send_voice_turn=AsyncMock(side_effect=cancelled))
            with patch("kcore.appliance._local_lan_ipv4",return_value="192.168.40.99") as discover:
                await app._run_voice_turn(body)
            self.assertEqual(body.send_voice_turn.call_args.kwargs["host"],"192.168.40.99" if auto else "127.0.0.1")
            self.assertEqual(discover.call_count,int(auto))
            await app.close()


if __name__=="__main__":unittest.main()
