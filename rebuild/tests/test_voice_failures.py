import asyncio
import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from kcore.appliance import ApplianceSettings, KadenceAppliance
from kcore.config import RuntimeConfig
from kcore.host import HostServer, Session, VoiceTurnFailure
from kcore.protocol import Envelope, MessageKind
from kcore.voice_providers import VoiceProviderSettings


class VoiceFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_ack_keeps_stage_and_releases_command_owner(self):
        host = HostServer(RuntimeConfig("127.0.0.1", 0, 5, 15))
        host._active_writer = object()
        host._active_session = Session("test", True)
        payload = {"ok": False, "network": False, "torque_released": True,
                   "stage": "wifi-config", "error_code": 12294, "wifi_reason": 8}
        async def reply(writer, command):
            host._resolve_pending(Envelope(MessageKind.ACK, command.name, payload, request_id=command.request_id))
        with patch.object(host, "_send", side_effect=reply):
            with self.assertRaises(VoiceTurnFailure) as failure:
                await host.send_voice_turn(ssid="test", password="test", host="127.0.0.1", port=1234)
            self.assertEqual(failure.exception.stage, "wifi-config")
            self.assertEqual(failure.exception.error_code, 12294)
            self.assertFalse(failure.exception.cancelled)
            self.assertFalse(host._command_lock.locked())
            self.assertEqual(host._pending, {})
            payload.update({name: True for name in ("ok", "network", "capture", "opus", "playback", "handoff")})
            self.assertTrue((await host.send_voice_turn(ssid="test", password="test", host="127.0.0.1", port=1234)).payload["ok"])

    async def test_cancelled_ack_is_not_retried_or_committed(self):
        settings = ApplianceSettings("COM4", 115200, 4800, 2, "test", "test", "127.0.0.1", VoiceProviderSettings("test", "test"))
        app = KadenceAppliance(settings)
        failure = VoiceTurnFailure(["ok", "capture"], {"stage": "cancelled", "cancelled": True, "torque_released": True})
        body = SimpleNamespace(send_voice_turn=AsyncMock(side_effect=failure), send_voice_cancel=AsyncMock(), send_body_pose=AsyncMock())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            await app._run_voice_turn(body)
        self.assertIn("TURN cancelled torque=released", output.getvalue())
        body.send_voice_cancel.assert_not_called()
        body.send_body_pose.assert_not_called()
        self.assertEqual(app._turn_sequence, 0)

    async def test_device_details_are_allowlisted_and_torque_still_required(self):
        failure = VoiceTurnFailure(["ok", "torque_released"], {"stage": "private credential",
            "error_code": "private", "wifi_reason": True, "cancelled": True})
        self.assertFalse(failure.cancelled)
        self.assertEqual(failure.stage, "unspecified")
        self.assertNotIn("private", str(failure))
        self.assertEqual(failure.error_code, 0)
        self.assertEqual(failure.wifi_reason, 0)

    async def test_missing_torque_proof_still_requests_physical_release(self):
        settings = ApplianceSettings("COM4", 115200, 4800, 2, "test", "test", "127.0.0.1", VoiceProviderSettings("test", "test"))
        app = KadenceAppliance(settings)
        failure = VoiceTurnFailure(["torque_released"], {"stage": "torque-release", "cancelled": True})
        body = SimpleNamespace(send_voice_turn=AsyncMock(side_effect=failure), send_voice_cancel=AsyncMock())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            await app._run_voice_turn(body)
        body.send_voice_cancel.assert_awaited_once()
        self.assertIn("TURN recovered", output.getvalue())


if __name__ == "__main__":
    unittest.main()
