"""A failed frame and a reboot must remain distinguishable without raw logs."""
import asyncio
import json
import struct
import unittest
from types import SimpleNamespace

from kcore.device_diagnostics import parse_device_diagnostic
from kcore.vision import IMAGE_BYTES, read_image
from kcore.serial_transport import SerialBodySession


class CameraDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def test_serial_observations_are_bounded_and_do_not_dispatch_protocol(self):
        events = []
        session = SerialBodySession(SimpleNamespace(), object(), port_name="COM4",
            diagnostic_sink=lambda n, d: events.append((n, d)))
        session._observe_diagnostic('{"kind":"ack","password":"secret"}')
        for _ in range(200): session._observe_diagnostic("Rebooting...")
        self.assertEqual(len(events), 128)
        self.assertTrue(all(e == ("device_diagnostic", {"reason": "rebooting"}) for e in events))
        self.assertTrue(session._events.empty())

    async def test_missing_frame_and_invalid_contract_have_distinct_reasons(self):
        cases = [
            (b"KDI0", RuntimeError, "image-header", "no-frame"),
            (b"xxxx", ValueError, "image-header", "bad-header"),
            (b"KDI1" + struct.pack("!HHI", 640, 480, IMAGE_BYTES), ValueError, "image-metadata", "bad-format"),
            (b"KDI1" + struct.pack("!HHI", 320, 240, IMAGE_BYTES) + b"fake pixels", asyncio.IncompleteReadError, "image-data", "truncated"),
        ]
        for data, error, stage, reason in cases:
            with self.subTest(reason=reason):
                events = []
                reader = asyncio.StreamReader(); reader.feed_data(data); reader.feed_eof()
                with self.assertRaises(error):
                    await read_image(reader, emit=lambda n, d: events.append(d))
                self.assertEqual(events[-1]["stage"], stage)
                self.assertEqual(events[-1]["reason"], reason)
                self.assertNotIn("fake pixels", json.dumps(events))
                if reason == "truncated": self.assertEqual(events[-1]["received_bytes"], 11)

    async def test_timeout_records_where_and_how_many_bytes_arrived(self):
        for header, stage, received in [
            (b"", "image-header", 0),
            (b"KDI1", "image-metadata", 0),
            (b"KDI1" + struct.pack("!HHI", 320, 240, IMAGE_BYTES) + b"pixels", "image-data", 6),
        ]:
            with self.subTest(stage=stage):
                events = []
                reader = asyncio.StreamReader(); reader.feed_data(header)
                with self.assertRaises(TimeoutError):
                    await asyncio.wait_for(read_image(reader, emit=lambda n, d: events.append(d)), .02)
                self.assertEqual(events[-1]["stage"], stage)
                self.assertEqual(events[-1]["received_bytes"], received)
                self.assertEqual(events[-1]["reason"], "interrupted")

    async def test_success_preserves_frame_without_exporting_pixels(self):
        events = []
        frame = b"\xf8\x00" * (320 * 240)
        reader = asyncio.StreamReader()
        reader.feed_data(b"KDI1" + struct.pack("!HHI", 320, 240, len(frame)) + frame)
        self.assertEqual(await read_image(reader, emit=lambda n, d: events.append(d)), frame)
        self.assertEqual(events[-1], {"stage": "image-complete", "received_bytes": IMAGE_BYTES, "expected_bytes": IMAGE_BYTES})
        self.assertEqual(len(events), 4)

    def test_reset_panic_and_driver_events_contain_no_raw_text(self):
        fixtures = [
            ("rst:0xc (SW_CPU_RESET),boot:0x8 (SPI_FAST_FLASH_BOOT)", {"reason": "reset", "reset_code": 12}),
            ("Rebooting...", {"reason": "rebooting"}),
            ("Guru Meditation Error: Core  1 panic'ed (Interrupt wdt timeout on CPU1).", {"reason": "interrupt-watchdog", "cpu": 1}),
            ("assert failed: FAKE_SECRET", {"reason": "assertion"}),
            ("\x1b[0;32mI (456) gc0308: Detected Camera sensor PID=0x9b\x1b[0m", {"reason": "sensor-detected", "component": "gc0308", "sensor_pid": 155}),
            ("E (456) dvp_cam: FAKE_SECRET", {"reason": "driver-error", "component": "dvp_cam"}),
            ("E (456) task_wdt: Task watchdog got triggered. FAKE_SECRET", {"reason": "task-watchdog"}),
            ("Backtrace: 0x42012345:0x3fce1234 0x40371234:0x3fce2345 FAKE_SECRET", {"reason": "backtrace", "backtrace": [0x42012345, 0x40371234]}),
        ]
        for line, expected in fixtures:
            self.assertEqual(parse_device_diagnostic(line), expected)
            self.assertNotIn("FAKE_SECRET", json.dumps(parse_device_diagnostic(line)))
        for line in ['{"password":"FAKE_SECRET"}', "I (123) wifi: FAKE_SECRET", "x" * 3000]:
            self.assertIsNone(parse_device_diagnostic(line))
