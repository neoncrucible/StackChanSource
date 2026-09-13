import asyncio
import copy
import unittest
from types import SimpleNamespace

from kcore.device_control import request_device
from kcore.protocol import Envelope, MessageKind
from kcore.sensors import SensorStatus, read_sensor_status


def payload():
    return dict(ok=True, schema=1, seq=2, age_ms=100, hub_address=0x71, hub="ready",
                hub_errors=0, upstream_mask=0,
                channels=[dict(state="ready", mask=0, errors=0) for _ in range(6)])


class SensorModelTests(unittest.TestCase):
    def test_addresses_are_evidence_and_stale_snapshots_are_visible(self):
        p = payload()
        p["channels"][0]["mask"] = 18
        result = SensorStatus.from_payload(p)
        self.assertEqual(result.channels[0].addresses, (0x44, 0x70))
        self.assertTrue(result.fresh)
        p["age_ms"] = 15001
        self.assertFalse(SensorStatus.from_payload(p).fresh)
        p["seq"] = 0; p["age_ms"] = 0
        self.assertFalse(SensorStatus.from_payload(p).fresh)

    def test_absent_hub_is_valid_status_with_no_downstream_evidence(self):
        p = payload(); p["hub"] = "absent"
        for ch in p["channels"]: ch["state"] = "unavailable"
        self.assertEqual(SensorStatus.from_payload(p).hub, "absent")
        p["channels"][0]["mask"] = 1
        with self.assertRaises(ValueError): SensorStatus.from_payload(p)

    def test_rejects_unbounded_ambiguous_and_unsupported_payloads(self):
        for key, bad in (("schema", True), ("schema", 2), ("seq", -1), ("age_ms", 2**32),
                         ("hub_address", 0x69), ("upstream_mask", 256), ("hub", "ok"),
                         ("channels", []), ("ok", 1)):
            p = payload(); p[key] = bad
            with self.subTest(key=key, value=bad), self.assertRaises(ValueError):
                SensorStatus.from_payload(p)
        for changes in (dict(mask=256), dict(mask=True), dict(state="quarantined", mask=1), dict(errors=-1)):
            p = payload(); p["channels"][0].update(changes)
            with self.assertRaises(ValueError): SensorStatus.from_payload(p)
        p = payload(); p["upstream_mask"] = p["channels"][0]["mask"] = 1
        with self.assertRaises(ValueError): SensorStatus.from_payload(p)
        p = payload(); p["hub_address"] = 0x70; p["channels"][0]["mask"] = 16
        with self.assertRaises(ValueError): SensorStatus.from_payload(p)


class FakeHost:
    def __init__(self):
        self._command_lock = asyncio.Lock()
        self._pending = {}
        self._active_writer = object()
        self._active_session = SimpleNamespace(hello_seen=True)
        self.reply = True
        self.retired = []
    async def _send(self, writer, command):
        if self.reply:
            response = Envelope(MessageKind.ACK, command.name, copy.deepcopy(payload()), request_id=command.request_id)
            self._pending[command.request_id].set_result(response)
    def _retire_request(self, ident): self.retired.append(ident)


class SensorTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_works_during_owned_voice_lane(self):
        host = FakeHost()
        async with host._command_lock:
            result = await asyncio.wait_for(read_sensor_status(host), .5)
        self.assertEqual(result.hub, "ready")
        self.assertEqual(host._pending, {})

    async def test_status_timeout_retires_request_and_rejects_mutation(self):
        host = FakeHost(); host.reply = False
        with self.assertRaises(TimeoutError): await read_sensor_status(host, timeout=.01)
        self.assertEqual(len(host.retired), 1)
        self.assertEqual(host._pending, {})
        with self.assertRaises(ValueError): await request_device(host, "sensors.status", {"scan": True})
        with self.assertRaises(ValueError): await request_device(host, "sensors.reset")
