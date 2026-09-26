"""Exercise failed LAN access, actual authenticated chimes and next-turn recovery."""
import asyncio
from dataclasses import replace
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from kcore import audio_network
from kcore.appliance import KadenceAppliance
from kcore.host import HostServer, Session, VoiceTurnFailure
from kcore.protocol import Envelope, MessageKind
from test_voice_recovery import settings


class AudioDevice:
    connected = True

    def __init__(self, app):
        self.app = app
        self.host = HostServer(__import__('kcore.appliance', fromlist=['_runtime_config'])._runtime_config())
        self.host._active_writer = object()
        self.host._active_session = Session("audio-link", True)
        self.host._send = self.send
        self.mode = "blocked"
        self.commands = []
        self.audio = []
        self.exchanges = []
        self.send_voice_cancel = AsyncMock(return_value=Envelope(MessageKind.ACK,"voice.cancel",{"ok":True,"torque_released":True}))

    async def send(self, writer, command):
        self.commands.append(command)
        async def exchange():
            proof = {"ok":True,"network":True,"handoff":True,"playback":True,"torque_released":True}
            if self.mode == "blocked":
                proof = {"ok":False,"stage":"tcp-connect","error_code":116,"torque_released":True}
            elif self.mode != "forged_ack":
                reader, stream = await asyncio.open_connection("127.0.0.1",self.app._server_port)
                try:
                    stream.write(b"KDA1"+command.payload["token"].encode()); await stream.drain()
                    self.assert_magic = await reader.readexactly(4)
                    size = struct.unpack("!I",await reader.readexactly(4))[0]
                    self.audio.append(await reader.readexactly(size))
                finally:
                    stream.close(); await stream.wait_closed()
            if self.mode == "lost_ack": return
            self.host._resolve_pending(Envelope(MessageKind.ACK, command.name, proof, request_id=command.request_id))
        task=asyncio.create_task(exchange());self.exchanges.append(task)


class AudioLinkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[]
        self.app=KadenceAppliance(settings(),emit=lambda n,d:self.events.append((n,d)))
        await self.app._start_voice_server()
        self.device=AudioDevice(self.app);self.app._body=self.device
        self.network=patch('kcore.appliance.inspect_windows',AsyncMock(return_value={"interfaces":[]}))
        self.network.start()

    async def asyncTearDown(self):
        self.app._body=None
        await self.app.close()
        await asyncio.gather(*self.device.exchanges,return_exceptions=True)
        self.network.stop()

    async def test_blocked_port_then_real_chime_without_reset_recording_or_provider(self):
        with patch('kcore.appliance.LiveVoiceProviders.from_settings',side_effect=AssertionError('No provider in link test')):
            with self.assertRaisesRegex(RuntimeError,'could not reach'):
                await self.app.test_audio_link()
            await asyncio.sleep(0)
            self.assertFalse(self.app._reconnect_requested.is_set())
            self.assertIsNone(self.app._turn_token)
            self.assertIsNone(self.app._voice_task)
            self.assertFalse(self.device.host._pending)
            self.assertFalse(self.device.host._command_lock.locked())
            self.assertIn(('voice_recovery',{'state':'network_required'}),self.events)
            self.device.mode='ok'
            result=await self.app.test_audio_link()
            self.assertEqual(result['state'],'passed')
            self.assertEqual(self.device.assert_magic,b'KDR1')
            self.assertEqual(len(self.device.audio[0]),32000)
            self.assertTrue(any(self.device.audio[0]))
            self.assertEqual([c.name for c in self.device.commands],['voice.alert','voice.alert'])
            self.assertEqual(self.app._turn_sequence,0)
            self.assertFalse(self.app._connections)
            self.assertIsNone(self.app._provider_task)

    async def test_lost_playback_ack_cannot_pass_and_releases_command_owner(self):
        self.device.mode='lost_ack'
        set_stage=self.app._set_voice_stage
        with patch.object(self.app,'_set_voice_stage',side_effect=lambda n,t:set_stage(n,.04 if n=='playback' else t)):
            with self.assertRaisesRegex(RuntimeError,'not confirmed'):
                await asyncio.wait_for(self.app.test_audio_link(),1)
        self.assertTrue(self.device.audio)
        self.assertFalse(self.device.host._pending)
        self.assertFalse(self.device.host._command_lock.locked())
        self.assertNotIn(('audio_link_test',{'state':'passed'}),self.events)
        self.device.mode='ok'
        self.assertEqual((await self.app.test_audio_link())['state'],'passed')

    async def test_ack_without_authenticated_media_is_not_a_success(self):
        self.device.mode='forged_ack'
        with self.assertRaisesRegex(RuntimeError,'not confirmed'):
            await self.app.test_audio_link()
        self.assertFalse(self.device.audio)
        self.assertFalse(any(n=='audio_link_test' and d['state']=='passed' for n,d in self.events))

    async def test_touch_cancel_during_chime_releases_ownership(self):
        self.device.mode='lost_ack'
        task=asyncio.create_task(self.app.test_audio_link())
        async with asyncio.timeout(1):
            while not self.device.audio:await asyncio.sleep(.001)
        await self.app._handle_touch_cancel(self.device,SimpleNamespace(payload={'trigger':'touch'}))
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertIsNone(self.app._voice_task)
        self.assertIsNone(self.app._turn_token)
        self.assertFalse(self.device.host._pending)
        self.device.mode='ok'
        self.assertEqual((await self.app.test_audio_link())['state'],'passed')

    async def test_normal_tcp_failure_keeps_usb_owner_and_accepts_next_attempt(self):
        failed=VoiceTurnFailure(['ok'],{'stage':'tcp-connect','error_code':116,'torque_released':True})
        self.device.send_voice_turn=AsyncMock(side_effect=failed)
        await self.app._run_voice_turn(self.device)
        self.assertFalse(self.app._reconnect_requested.is_set())
        self.assertEqual(self.device.send_voice_cancel.await_count,0)
        self.assertIsNone(self.app._turn_token)
        await self.app._run_voice_turn(self.device)
        self.assertEqual(self.device.send_voice_turn.await_count,2)

    async def test_stale_explicit_address_fails_before_sending_credentials(self):
        self.app.settings=replace(self.app.settings,lan_host='192.0.2.244')
        self.device.send_voice_turn=AsyncMock()
        await self.app._run_voice_turn(self.device)
        self.device.send_voice_turn.assert_not_called()
        self.device.send_voice_cancel.assert_not_called()
        self.assertFalse(self.app._reconnect_requested.is_set())
        self.assertIn(('runtime_issue',{'stage':'voice','reason':'address_not_local'}),self.events)


class NetworkTests(unittest.TestCase):
    def test_route_selection_handles_vpn_and_camera_usb_without_overriding_an_explicit_setting(self):
        rows=[{'address':'10.8.0.2','physical':False,'gateway':True,'network':'VPN'},
              {'address':'10.254.239.2','physical':True,'gateway':False,'network':'Camera'},
              {'address':'192.168.40.9','physical':True,'gateway':True,'network':'Robot WiFi'}]
        with patch('kcore.audio_network.address_is_local',return_value=True):
            self.assertEqual(audio_network.select_address('10.8.0.2',rows,'Robot WiFi'),'192.168.40.9')
            rows.append({'address':'192.168.60.9','physical':True,'gateway':True,'network':'Other'})
            self.assertEqual(audio_network.select_address('10.8.0.2',rows,'Robot WiFi'),'192.168.40.9')
            self.assertEqual(audio_network.select_address('192.168.60.9',rows,'Unknown'),'192.168.60.9')

    def test_reports_configuration_without_claiming_robot_reachability_and_redacts_addresses(self):
        snapshot={'interfaces':[{'address':'127.0.0.1','profile':'private'}], 'firewall':'checked','rules':[]}
        options={'host':'127.0.0.1','port':54321,'automatic':True,'listening':True}
        self.assertEqual(audio_network.network_report(snapshot,**options)['state'],'no_allow_rule')
        snapshot['rules']=[{'profiles':2,'ports':'*','action':'allow','application':True}]
        result=audio_network.network_report(snapshot,**options)
        self.assertEqual(result['state'],'allow_rule_present')
        self.assertIn('Test Audio Link',result['message'])
        self.assertNotIn('127.0.0.1',str(audio_network.diagnostic({**result,'ssid':'PRIVATE','password':'SECRET'})))
        snapshot['rules'].append({'profiles':2,'ports':'54320-54322','action':'block'})
        self.assertEqual(audio_network.network_report(snapshot,**options)['state'],'block_rule')
        snapshot['interfaces'][0]['profile']='public'
        self.assertEqual(audio_network.network_report(snapshot,**options)['state'],'public_network')

    def test_local_address_probe_and_malicious_diagnostic_content(self):
        self.assertTrue(audio_network.address_is_local('127.0.0.1'))
        for value in ('0.0.0.0','224.0.0.1','169.254.1.2','192.0.2.244','$(bad)'):
            self.assertFalse(audio_network.address_is_local(value))
        self.assertEqual(audio_network.diagnostic({'state':'PRIVATE','profile':'SECRET','interfaces':True,'host':'SECRET'}),{})


@unittest.skipUnless(sys.platform=='win32','Windows firewall COM validation without rule changes')
class WindowsNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_windows_rule_construction_is_private_local_tcp_and_does_not_register(self):
        report=await audio_network._powershell('Validate')
        self.assertTrue(report['rule_validated']);self.assertTrue(report['program_matches'])
        self.assertEqual((report['profiles'],report['protocol'],report['direction'],report['action']),(2,6,1,1))
        self.assertEqual(report['remote'].lower(),'localsubnet');self.assertFalse(report['edge'])
        # The actual read-only helper must execute, not a mocked cmdlet response.
        report=await audio_network._powershell('Inspect')
        self.assertIn(report['firewall'],{'checked','unknown'})
        self.assertIsInstance(report['interfaces'],list)
