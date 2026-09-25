import asyncio
from dataclasses import asdict
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from kcore.appliance import ApplianceSettings, KadenceAppliance
from kcore.camera_manager import CameraConfig, CameraManager
from kcore.perception import PerceptionController
from kcore.reflex import ReflexController
from kcore.schema import ensure_schema
from kcore.sensor_sampler import SensorSampler
from kcore.sensors import GestureStatus, TofStatus
from kcore.storage import KadencePaths
from kcore.voice_providers import VoiceProviderSettings


def tof(seq, distance=600):
    return TofStatus("ready", seq, 0, 0, 9, True, distance)


def gesture(seq):
    return GestureStatus("ready", seq + 1, 0, seq, 0, 1)


@pytest.mark.parametrize("policy", ["OFF", "EVENT_ONLY", "AWARE"])
@pytest.mark.parametrize("privacy", [False, True])
def test_live_pipeline_observes_without_camera_cv_speech_motion_or_llm(tmp_path, policy, privacy):
    async def case():
        now = [0.0]; events = []
        paths = KadencePaths.for_root(tmp_path); ensure_schema(paths)
        capture = AsyncMock(side_effect=AssertionError("No automatic camera work"))
        deliver = AsyncMock(side_effect=AssertionError("No greeting or movement"))
        faces = SimpleNamespace(health="not_loaded", analyze=lambda _: pytest.fail("No CV"))
        camera = CameraManager(capture, config=CameraConfig(policy=policy, privacy=privacy, greetings=True, unknown_alerts=True))
        sampler = SensorSampler(lambda *args: events.append(args), clock=lambda: now[0])
        pc = PerceptionController(camera, paths, lambda *args: events.append(args), deliver,
                                  lambda: False, faces=faces, clock=lambda: now[0], sampler=sampler)
        await pc.start()
        for second in range(131):
            now[0] = float(second)
            observation = sampler.sample(tof(second + 1, 250 if 20 <= second < 30 else 600), gesture(second // 10))
            await pc.sample(observation)
            await pc.tick()
        assert not pc.request("arrival") and not pc.request("gesture") and not pc.request("heartbeat")
        await pc.dispatch(camera.generation)
        capture.assert_not_called(); deliver.assert_not_called()
        assert pc.task is None and not pc.budget.requests
        assert sampler.reflex.counts["arrivals"] == 1
        assert sampler.reflex.counts["gestures"] == 13
        assert sampler.reflex.counts["approaches"] == 1
        with sqlite3.connect(paths.database) as db:
            assert db.execute("PRAGMA user_version").fetchone()[0] == 4
            for table in ("media", "presence_sessions", "perception_actions"):
                assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
            rows = db.execute("SELECT evidence_json,presence_session_id FROM perception_events WHERE event_type='reflex_proposed'").fetchall()
            assert len(rows) == 15  # Decisions only, not 131 samples.
            assert all(json.loads(row[0])["mode"] == "OBSERVE_ONLY" and row[1] is None for row in rows)
        await pc.close()
    asyncio.run(case())


def test_stale_timer_preserves_visit_and_resume_reset_ends_it(tmp_path):
    async def case():
        now = [0.0]
        paths = KadencePaths.for_root(tmp_path); ensure_schema(paths)
        pc = PerceptionController(CameraManager(None), paths, lambda *args: None, AsyncMock(), lambda: False, clock=lambda: now[0])
        await pc.start()
        for second in range(3):
            now[0] = second
            await pc.sample(pc.sampler.sample(tof(second + 1)))
            await pc.tick()
        session = pc.sampler.reflex.session_id
        now[0] = 8; await pc.tick()
        assert pc.occupancy.state == "UNKNOWN" and pc.sampler.reflex.session_id == session
        now[0] = 30; await pc.tick()
        assert pc.sampler.reflex.session_id is None
        with sqlite3.connect(paths.database) as db:
            events = [json.loads(row[0]) for row in db.execute("SELECT evidence_json FROM perception_events WHERE event_type='reflex_proposed'")]
        assert [(e["type"], e["reason"]) for e in events] == [("arrival", "confirmed_arrival"), ("session_ended", "resume")]
        await pc.close()
    asyncio.run(case())


@pytest.mark.parametrize("bad_sensor", ["tof", "gesture"])
def test_appliance_keeps_the_other_sensor_and_uses_one_upstream_sampler(bad_sensor):
    async def case():
        settings = ApplianceSettings("COM4", 115200, 4800, 2, "test", "test", "127.0.0.1", VoiceProviderSettings("test", "test"))
        app = KadenceAppliance(settings)
        app._body = SimpleNamespace(host=object(), connected=True)
        app.perception = SimpleNamespace(sample=AsyncMock())
        tof_read = AsyncMock(return_value=tof(1))
        gesture_read = AsyncMock(return_value=gesture(1))
        (tof_read if bad_sensor == "tof" else gesture_read).side_effect = OSError("sensor unavailable")
        with patch("kcore.sensors.read_tof_status", tof_read), patch("kcore.sensors.read_gesture_status", gesture_read):
            await app._sample_sensors(app._body)
        tof_read.assert_awaited_once(); gesture_read.assert_awaited_once()
        app.perception.sample.assert_awaited_once()
        assert app.sensor_sampler.reflex.counts["samples"] == 1
        if bad_sensor == "gesture":
            assert app.sensor_sampler.occupancy.state == "ARRIVAL_CANDIDATE"
        else:
            assert app.sensor_sampler.occupancy.state == "UNKNOWN"
    asyncio.run(case())


@pytest.mark.parametrize("stop_during_read", [False, True])
def test_disconnected_or_stopping_body_cannot_deliver_late_sensor_samples(stop_during_read):
    async def case():
        settings = ApplianceSettings("COM4", 115200, 4800, 2, "test", "test", "127.0.0.1", VoiceProviderSettings("test", "test"))
        app = KadenceAppliance(settings)
        old_body = SimpleNamespace(host=object(), connected=True)
        app._body = SimpleNamespace(host=object(), connected=True)
        app.perception = SimpleNamespace(sample=AsyncMock())
        if stop_during_read: app._body = old_body
        async def read_tof(*args, **kwargs):
            if stop_during_read: app._stop.set()
            return tof(1)
        with patch("kcore.sensors.read_tof_status", side_effect=read_tof), patch("kcore.sensors.read_gesture_status", AsyncMock(return_value=gesture(1))):
            await app._sample_sensors(old_body)
        app.perception.sample.assert_not_called()
        assert app.sensor_sampler.reflex.counts["samples"] == 0
    asyncio.run(case())


def test_console_retains_bounded_proposals_separately_from_device_spam(tmp_path):
    from PySide6.QtWidgets import QApplication, QFileDialog
    from kcore.desktop_ui import MainWindow
    qt = QApplication.instance() or QApplication([])
    window = MainWindow(directory=tmp_path, load_credentials=False)
    try:
        reflex = ReflexController(wall_clock=lambda: 1000)
        reflex.observe("UNKNOWN", None, gesture(0), 0)
        for index in range(1, 131):
            event = reflex.observe("UNKNOWN", None, gesture(index), index * 4)[0]
            window.on_event("reflex_event", {**event.payload(), "prompt": "secret", "name": "private-name"})
        window.on_event("reflex_status", {**reflex.status(), "credential": "secret"})
        for _ in range(500):
            window.on_event("device", {"presentation": "idle"})
        assert len(window.reflex_events) == 120 and len(window.diagnostic) == 400
        assert "Proposals 130" in window.reflex_counts.text()
        assert "OBSERVE_ONLY" in str(window.reflex_snapshot)
        output = tmp_path / "diagnostics.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output), "")):
            window.export_diagnostics()
        data = json.loads(output.read_text())
        assert len(data["reflex"]["events"]) == 120
        assert "secret" not in output.read_text() and "private-name" not in output.read_text()
        window.on_event("camera_settings", asdict(CameraConfig(policy="AWARE", privacy=True)))
        assert window.camera_privacy.isChecked()
        window.navigate(3); window.show(); qt.processEvents()
        assert window.reflex_counts.isVisible()
    finally:
        window.ticker.stop(); window.quitting = True; window.close()
