"""Focused offline release gate; no hardware, credentials or live integrations."""
from pathlib import Path
import io
import contextlib
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "backend"))


def main() -> int:
    suite=unittest.TestSuite()
    loader=unittest.TestLoader()
    for pattern in ("test_phase_b.py", "test_appliance_candidate.py", "test_integrations.py", "test_package_firmware.py", "test_context_store.py", "test_appliance_setup.py", "test_voice_failures.py"):
        suite.addTests(loader.discover(str(ROOT / "tests"),pattern=pattern))
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream):
        result=unittest.TextTestRunner(stream=stream,verbosity=1).run(suite)
    if not result.wasSuccessful():
        print(stream.getvalue())
        return 1
    print(f"PHASE_B_GATE PASS tests={result.testsRun} boundary=1 confirmation=1 persistence=1 "
          "auth=1 voice_lifecycle=1 cancel=1 recovery=1 hardware=unproven")
    return 0


if __name__=="__main__": raise SystemExit(main())
