import contextlib
import io
import os
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from kcore import appliance


class SetupTests(unittest.TestCase):
    def args(self, *extra):
        with patch("sys.argv", ["kadence", *extra]):
            return appliance._parse_args()

    def test_visible_input_reaches_all_credential_prompts_without_persistence(self):
        values = ["test-openai", "test-gemini", "test-wifi-password"]
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(appliance.sys.stdin, "isatty", return_value=True), \
             patch.object(appliance, "_current_wifi_ssid", return_value="test-ssid"), \
             patch.object(appliance, "_local_lan_ipv4", return_value="192.0.2.10"), \
             patch("builtins.input", side_effect=values) as visible, \
             patch.object(appliance.getpass, "getpass") as hidden, \
             contextlib.redirect_stdout(output):
            settings = appliance._make_settings(self.args("--visible-input"))
            self.assertEqual([call.args[0] for call in visible.call_args_list],
                             ["OpenAI API key: ", "Gemini API key: ", "Wi-Fi password: "])
            hidden.assert_not_called()
            self.assertEqual(settings.password, values[2])
            self.assertEqual(settings.providers.openai_api_key, values[0])
            self.assertEqual(settings.providers.gemini_api_key, values[1])
            self.assertEqual(dict(os.environ), {})
        self.assertIn("Input is visible", output.getvalue())
        for value in values:
            self.assertNotIn(value, output.getvalue() + repr(settings))

    def test_default_input_remains_hidden(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(appliance.sys.stdin, "isatty", return_value=True), \
             patch.object(appliance, "_current_wifi_ssid", return_value="test-ssid"), \
             patch.object(appliance, "_local_lan_ipv4", return_value="192.0.2.10"), \
             patch("builtins.input") as visible, \
             patch.object(appliance.getpass, "getpass", side_effect=["test-openai", "test-gemini", "test-wifi"]) as hidden, \
             contextlib.redirect_stdout(io.StringIO()):
            appliance._make_settings(self.args())
            visible.assert_not_called()
            self.assertEqual(hidden.call_count, 3)

    def test_missing_timezone_package_stops_before_credential_entry(self):
        real_import = appliance.importlib.import_module

        def without_timezone(name):
            if name == "tzdata":
                raise ModuleNotFoundError("No module named 'tzdata'")
            return real_import(name)

        output = io.StringIO()
        with patch.object(appliance.importlib, "import_module", side_effect=without_timezone), \
             patch("sys.argv", ["kadence", "--visible-input"]), \
             patch("builtins.input") as visible, \
             patch.object(appliance.getpass, "getpass") as hidden, \
             contextlib.redirect_stdout(output):
            self.assertEqual(appliance.main(), 2)
        visible.assert_not_called()
        hidden.assert_not_called()
        self.assertIn("NEEDS_SETUP", output.getvalue())
        self.assertIn("tzdata", output.getvalue())
        self.assertIn(appliance.sys.executable, output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_invalid_timezone_is_a_setup_error(self):
        with patch.object(appliance, "ZoneInfo", side_effect=ZoneInfoNotFoundError), \
             patch("sys.argv", ["kadence", "--check"]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(appliance.main(), 2)
        self.assertIn("timezone unavailable", output.getvalue())

    def test_check_needs_no_credentials_or_hardware(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("sys.argv", ["kadence", "--check"]), \
             patch.object(appliance, "_make_settings") as settings, \
             patch.object(appliance, "KadenceAppliance") as runtime, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(appliance.main(), 0)
        settings.assert_not_called()
        runtime.assert_not_called()
        self.assertIn("CHECK PASS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
