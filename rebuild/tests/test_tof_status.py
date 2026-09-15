import asyncio
import unittest
from types import SimpleNamespace

from kcore.device_control import request_device
from kcore.protocol import Envelope, MessageKind
from kcore.sensors import TofStatus, read_tof_status


def payload():
    return dict(ok=True, schema=1, state="ready", channel=1, address=0x29,
                seq=3, age_ms=100, errors=0, raw_status=9, valid=True, distance_mm=450)


class TofTests(unittest.TestCase):
    def test_freshness_is_separate_from_measurement_quality(self):
        p = payload()
        self.assertTrue(TofStatus.from_payload(p).fresh)
        p.update(valid=False, distance_mm=None, raw_status=4)
        s = TofStatus.from_payload(p)
        self.assertTrue(s.fresh)
        self.assertFalse(s.valid)
        self.assertIsNone(s.distance_mm)
        p["age_ms"] = 3001
        self.assertFalse(TofStatus.from_payload(p).fresh)
        p.update(age_ms=0, seq=0, state="starting")
        self.assertFalse(TofStatus.from_payload(p).fresh)

    def test_rejects_wrong_chip_wiring_types_and_impossible_valid_readings(self):
        for key, value in (("schema", True), ("channel", 0), ("address", 0x73),
                           ("seq", 0), ("seq", -1), ("age_ms", 2**32), ("errors", -1),
                           ("raw_status", 4), ("raw_status", 32), ("valid", 1),
                           ("state", "fault"), ("distance_mm", 39), ("distance_mm", 4001),
                           ("distance_mm", None), ("distance_mm", True), ("distance_mm", 450.0)):
            p = payload(); p[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                TofStatus.from_payload(p)
        p = payload(); p["valid"] = False
        with self.assertRaises(ValueError): TofStatus.from_payload(p)
        p = payload(); p["extra"] = "ignored?"
        with self.assertRaises(ValueError): TofStatus.from_payload(p)


class Host:
    def __init__(self):
        self._command_lock = asyncio.Lock()
        self._pending = {}
        self._active_writer = object()
        self._active_session = SimpleNamespace(hello_seen=True)
        self.reply = True
        self.retired = []

    async def _send(self, writer, command):
        if self.reply:
            self._pending[command.request_id].set_result(
                Envelope(MessageKind.ACK, command.name, payload(), request_id=command.request_id))

    def _retire_request(self, ident):
        self.retired.append(ident)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_query_does_not_wait_for_voice_lane(self):
        host = Host()
        async with host._command_lock:
            s = await asyncio.wait_for(read_tof_status(host), 0.5)
        self.assertEqual(s.distance_mm, 450)
        self.assertEqual(host._pending, {})

    async def test_timeout_and_mutation_are_rejected(self):
        host = Host(); host.reply = False
        with self.assertRaises(TimeoutError): await read_tof_status(host, timeout=0.01)
        self.assertEqual(len(host.retired), 1)
        self.assertEqual(host._pending, {})
        with self.assertRaises(ValueError): await request_device(host, "sensors.tof", {"start": True})
