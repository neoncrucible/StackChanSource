import unittest

from kcore.desktop_worker import camera_diagnostic_event
from kcore.serial_transport import parse_camera_diagnostic


class CameraDiagnosticTests(unittest.TestCase):
    def test_stage_log_is_bounded_and_mapped_to_existing_schema(self):
        parsed = parse_camera_diagnostic(
            "I (123) kade: CAMERA_DIAG stage=controller-started "
            "stack_min_free_bytes=28000 internal_free=154321 internal_largest=120000 "
            "psram_free=7000000 psram_largest=6500000 ignored=secret"
        )
        self.assertEqual(parsed["stage"], "controller-started")
        self.assertNotIn("ignored", parsed)
        event = camera_diagnostic_event(parsed)
        self.assertEqual(event, {
            "stage": "camera", "reason": "device_proof", "error_code": 21,
            "free_heap": 154321, "free_psram": 7000000,
        })

    def test_failure_log_uses_same_checkpoint_namespace(self):
        parsed = parse_camera_diagnostic(
            "E (456) kade: CAMERA_DIAG failure=controller-start err=ESP_FAIL"
        )
        self.assertEqual(parsed, {
            "kind": "diag", "stage": "controller-start", "error": "ESP_FAIL"
        })
        self.assertEqual(camera_diagnostic_event(parsed)["error_code"], 20)

    def test_power_readback_is_packed_without_raw_log_text(self):
        parsed = parse_camera_diagnostic(
            "I (10) kade: CAMERA_POWER pmic_enable_ok=1 pmic_enable=0xBF "
            "pmic_camera_ok=1 pmic_camera=0x1C expander_output_ok=1 "
            "expander_output=0x01 expander_config_ok=1 expander_config=0x00"
        )
        event = camera_diagnostic_event(parsed)
        self.assertEqual(event["stage"], "camera")
        self.assertEqual(event["reason"], "device_proof")
        self.assertEqual(event["error_code"], (0xF << 32) | 0xBF1C0100)
        self.assertEqual(set(event), {"stage", "reason", "error_code"})

    def test_unrelated_and_unbounded_tokens_are_ignored(self):
        self.assertIsNone(parse_camera_diagnostic("WIFI password=hunter2"))
        parsed = parse_camera_diagnostic(
            "CAMERA_DIAG stage=" + "x" * 100 + " internal_free=-1 psram_free=999999999999"
        )
        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
