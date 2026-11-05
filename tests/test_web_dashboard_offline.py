"""Offline FastAPI operator console tests."""

from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from ls55.service import LS55Service
from ls55.web.app import create_app

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_api_state_and_review_recompute(tmp_path):
    logs = tmp_path / "logs"
    (logs / "freepath").mkdir(parents=True)
    csv_path = logs / "freepath" / "demo.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["wavelength_nm", "sample_on", "blank", "corrected"])
        for i in range(20):
            wl = 400.0 + 2.0 * i
            writer.writerow([wl, 1000 + i, 10, 990 + i])

    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=logs)
    with TestClient(app) as client:
        state = client.get("/api/state")
        assert state.status_code == 200
        body = state.json()
        assert body["state"] == "disconnected"
        assert "ports" in body

        blanks = client.get("/api/blanks")
        assert blanks.status_code == 200
        assert any(b["name"] == "demo.csv" for b in blanks.json()["blanks"])

        rev = client.post(
            "/api/review/recompute",
            json={
                "csv_path": str(csv_path),
                "guide_nm": 420.0,
                "half_window_nm": 20.0,
                "noise_lo_nm": 430.0,
                "noise_hi_nm": 438.0,
                "wing_left": [400.0, 406.0],
                "wing_right": [430.0, 438.0],
            },
        )
        assert rev.status_code == 200, rev.text
        data = rev.json()
        assert data["peak_nm"] is not None
        assert len(data["wavelength_nm"]) == 20

        index = client.get("/")
        assert index.status_code == 200
        assert b"LS 55 Operator Console" in index.content


def test_demo_session_connect_setup_scout_scan(tmp_path):
    """Offline power-on → optics → scout → scan path used by the operator console."""
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        state = client.get("/api/state")
        assert state.status_code == 200
        assert "demo_session" in state.json()["fixtures"]

        conn = client.post(
            "/api/connect",
            json={
                "fixture_dir": str(FIXTURES / "demo_session"),
                "gate_a_pass": True,
                "compartment_closed": True,
            },
        )
        assert conn.status_code == 200, conn.text
        body = conn.json()
        assert body["ok"] is True
        assert body["discover"]["first_power_on"] is True
        assert client.get("/api/state").json()["state"] == "idle_safe"
        assert client.get("/api/state").json()["es_position"] == 1

        setup = client.post(
            "/api/setup",
            json={"ex_nm": 350.0, "em_nm": 400.0, "ex_slit": 5.0, "em_slit": 5.0},
        )
        assert setup.status_code == 200, setup.text
        assert setup.json()["ok"] is True

        scout = client.post(
            "/api/single-read",
            json={
                "ex_nm": 350.0,
                "em_nm": 450.0,
                "integration_s": 1.0,
                "dark_correct": True,
            },
        )
        assert scout.status_code == 200, scout.text
        scout_body = scout.json()
        assert scout_body["ok"] is True
        assert scout_body["corrected"] == 128397.0
        assert scout_body["clipped"] is False

        scan = client.post(
            "/api/scan",
            json={
                "mx": 1,
                "ex_nm": 350.0,
                "em_lo": 400.0,
                "em_hi": 550.0,
                "interval_nm": 2.0,
                "speed": 120,
                "ex_slit": 5.0,
                "em_slit": 5.0,
                "include_dark": True,
                "n_accumulate": 1,
            },
        )
        assert scan.status_code == 200, scan.text
        scan_body = scan.json()
        assert scan_body["passed"] is True, scan_body.get("errors")
        assert scan_body["sample"]["intensity"][0] == 1200
        assert client.get("/api/state").json()["es_position"] == 1


def test_abort_when_disconnected_does_not_500(tmp_path):
    """Power/USB are dynamic — Abort must not crash before a session exists."""
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        abort = client.post("/api/abort", json={})
        assert abort.status_code == 200, abort.text
        body = abort.json()
        assert "ok" in body
        # No adapter in CI → ephemeral clear reports missing port, not a 500.
        if body.get("ephemeral"):
            assert body["ok"] is False
            assert body.get("errors")


def test_probe_forces_xe_off_when_ready_after_power_on(tmp_path):
    """Ready probe must kill Xe (Stage 0 resting / post-loss policy)."""
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        probe = client.post(
            "/api/probe",
            json={
                "fixture_dir": str(FIXTURES / "discover_first_power_on"),
                "boot_wait_s": 1,
            },
        )
        assert probe.status_code == 200, probe.text
        body = probe.json()
        assert body["ready"] is True
        assert body["es_position"] == 1
        assert body["first_power_on"] is True
        assert body["link_settled"] is True
        state = client.get("/api/state").json()
        assert state["es_position"] == 1
        assert state["xe_kill_pending"] is False
        assert state["link_settled"] is True
        assert state["recovering"] is False
        logs = list((tmp_path / "dashboard").glob("probe-*.log"))
        assert logs
        text = logs[-1].read_text(encoding="utf-8")
        assert "$ES 1" in text


def test_link_settled_stops_heartbeat_and_resumes_after_command_failure(tmp_path):
    """Settled after Xe OFF: no idle heartbeat; command failure recovers via probe."""
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        probe = client.post(
            "/api/probe",
            json={
                "fixture_dir": str(FIXTURES / "discover_ready_off"),
                "boot_wait_s": 1,
            },
        )
        assert probe.status_code == 200, probe.text
        assert probe.json()["link_settled"] is True
        assert client.get("/api/state").json()["link_settled"] is True

        # Idle heartbeat must be a no-op while settled (command-driven loss only).
        before = service.snapshot().to_dict()
        service._maybe_heartbeat()
        after = service.snapshot().to_dict()
        assert after["link_settled"] is True
        assert after["es_position"] == before["es_position"]

        # Simulated later command failure → recovering, not settled.
        service._maybe_unsettle_from_failure("serial timeout during status refresh")
        mid = client.get("/api/state").json()
        assert mid["link_settled"] is False
        assert mid["recovering"] is True

        # Ready+OFF probe settles again.
        probe2 = client.post(
            "/api/probe",
            json={
                "fixture_dir": str(FIXTURES / "discover_ready_off"),
                "boot_wait_s": 1,
            },
        )
        assert probe2.status_code == 200, probe2.text
        assert probe2.json()["ready"] is True
        assert probe2.json()["es_position"] == 1
        done = client.get("/api/state").json()
        assert done["link_settled"] is True
        assert done["recovering"] is False


def test_disconnect_clears_link_settled(tmp_path):
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/connect",
            json={
                "fixture_dir": str(FIXTURES / "identity_happy"),
                "gate_a_pass": True,
                "compartment_closed": True,
            },
        )
        assert resp.status_code == 200, resp.text
        assert client.get("/api/state").json()["link_settled"] is True

        disc = client.post("/api/disconnect", json={})
        assert disc.status_code == 200
        state = client.get("/api/state").json()
        assert state["link_settled"] is False
        assert state["recovering"] is False
        assert state["state"] == "disconnected"


def test_busy_probe_sets_xe_kill_pending(tmp_path):
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        probe = client.post(
            "/api/probe",
            json={
                "fixture_dir": str(FIXTURES / "discover_busy"),
                "boot_wait_s": 1,
            },
        )
        assert probe.status_code == 200, probe.text
        assert probe.json()["state"] == "busy"
        state = client.get("/api/state").json()
        assert state["xe_kill_pending"] is True
        assert state["es_position"] is None


def test_probe_and_connect_detect_busy_without_forcing_es(tmp_path):
    """Busy 0110 must be classified; failed connect must not send $ES."""
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        probe = client.post(
            "/api/probe",
            json={
                "fixture_dir": str(FIXTURES / "discover_busy"),
                "boot_wait_s": 1,
            },
        )
        assert probe.status_code == 200, probe.text
        pbody = probe.json()
        assert pbody["state"] == "busy"
        assert pbody["job_running"] is True
        assert pbody["ready"] is False
        assert pbody.get("es_position") is None
        assert client.get("/api/state").json()["es_position"] is None

        busy = client.post(
            "/api/connect",
            json={
                "fixture_dir": str(FIXTURES / "discover_busy"),
                "gate_a_pass": True,
                "compartment_closed": True,
                "boot_wait_s": 1,
            },
        )
        assert busy.status_code == 400
        detail = busy.json()["detail"].lower()
        assert "0110" in detail or "busy" in detail

        state = client.get("/api/state").json()
        assert state["link"]["state"] == "busy"
        # Session log must not include $ES (busy policy: leave shutter alone).
        logs = list((tmp_path / "dashboard").glob("session-*.log"))
        assert logs
        text = logs[-1].read_text(encoding="utf-8")
        assert "$ES" not in text
        assert "$ST" in text


def test_connect_busy_message_and_identity_abort(tmp_path):
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        bad = client.post(
            "/api/connect",
            json={
                "fixture_dir": str(FIXTURES / "identity_happy"),
                "gate_a_pass": False,
            },
        )
        assert bad.status_code == 400

        resp = client.post(
            "/api/connect",
            json={
                "fixture_dir": str(FIXTURES / "identity_happy"),
                "gate_a_pass": True,
                "compartment_closed": True,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        state = client.get("/api/state").json()
        assert state["state"] == "idle_safe"
        assert state["es_position"] == 1

        abort = client.post("/api/abort", json={})
        assert abort.status_code == 200

        off = client.post("/api/shutter/off", json={})
        assert off.status_code == 200
        assert off.json()["ok"] is True


def test_xe_kill_pending_and_extension_emergency_stop(tmp_path):
    from ls55.service import LS55Service

    class ProbeExt:
        name = "probe_ext"

        def __init__(self) -> None:
            self.stopped = False
            self.pre = 0
            self.post = 0

        def connect(self) -> None:
            return None

        def get_state(self) -> dict:
            return {"ok": True}

        def pre_acquire(self, context: dict) -> None:
            self.pre += 1

        def post_acquire(self, context: dict) -> None:
            self.post += 1

        def emergency_stop(self) -> None:
            self.stopped = True

    service = LS55Service(log_dir=tmp_path / "dashboard")
    ext = ProbeExt()
    service.register_extension(ext)  # type: ignore[arg-type]
    assert "probe_ext" in service.extensions

    service._note_connection_loss()
    snap = service.snapshot().to_dict()
    assert snap["xe_kill_pending"] is True
    assert snap["es_position"] is None

    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        # Connect clears pending via discover force-off.
        resp = client.post(
            "/api/connect",
            json={
                "fixture_dir": str(FIXTURES / "identity_happy"),
                "gate_a_pass": True,
                "compartment_closed": True,
            },
        )
        assert resp.status_code == 200, resp.text
        state = client.get("/api/state").json()
        assert state["xe_kill_pending"] is False
        assert state["es_position"] == 1

        abort = client.post("/api/abort", json={})
        assert abort.status_code == 200
        assert ext.stopped is True


def test_ws_telemetry_hello(tmp_path):
    service = LS55Service(log_dir=tmp_path / "dashboard")
    app = create_app(service=service, logs_root=tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            msg = ws.receive_json()
            assert msg["event"] == "hello"
            assert "payload" in msg
            assert msg["payload"]["state"] == "disconnected"
