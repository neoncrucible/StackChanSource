import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from kcore.appliance import KadenceAppliance, ApplianceSettings
from kcore.voice_providers import VoiceProviderSettings

class Routing(unittest.IsolatedAsyncioTestCase):
    def app(self, mode):
        app=KadenceAppliance(ApplianceSettings("COM4",115200,4800,2,"test","","127.0.0.1",VoiceProviderSettings(None,None)))
        # Replace settings without making platform-specific output calls.
        from types import SimpleNamespace
        app.settings=SimpleNamespace(audio_output=mode)
        app._windows_audio=Mock()
        return app

    async def test_outputs_and_failure_stop(self):
        pcm=b'\x01\x00'*100
        for mode in ('robot','windows','both'):
            with self.subTest(mode=mode):
                app=self.app(mode); writer=Mock()
                with patch('kcore.appliance.send_wire_reply',new_callable=AsyncMock) as send:
                    await app._send_speech(writer,pcm)
                    send.assert_awaited_once_with(writer, bytes(len(pcm)) if mode=='windows' else pcm)
                if mode=='robot': app._windows_audio.start.assert_not_called()
                else: app._windows_audio.start.assert_called_once_with(pcm)
        app=self.app('both')
        with patch('kcore.appliance.send_wire_reply',new_callable=AsyncMock,side_effect=ConnectionError):
            with self.assertRaises(ConnectionError): await app._send_speech(Mock(),pcm)
        app._windows_audio.stop.assert_called_once()

    async def test_cancel_stops_windows_even_without_provider_task(self):
        app=self.app('both')
        await app._cancel_active_provider()
        app._windows_audio.stop.assert_called_once()
