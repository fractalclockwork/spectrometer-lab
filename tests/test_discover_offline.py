"""Offline discovery / readiness checks against synthetic fixtures."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ls55.discover import list_candidate_ports, run_discover
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_list_candidate_ports_ignores_platform_uarts(monkeypatch):
    """Unplugged USB must not report motherboard ttyS* as adapters."""
    real_is_dir = Path.is_dir

    def _is_dir(self: Path) -> bool:
        if str(self) == "/dev/serial/by-id":
            return False
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", _is_dir)

    fake_mod = SimpleNamespace(
        comports=lambda: [
            SimpleNamespace(device="/dev/ttyS0", vid=None, hwid="PNP0501"),
            SimpleNamespace(device="/dev/ttyUSB0", vid=0x067B, hwid="USB VID:PID=067B:2303"),
            SimpleNamespace(device="/dev/ttyACM0", vid=0x2341, hwid="USB VID:PID=2341:0043"),
        ]
    )
    import sys

    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(tools=SimpleNamespace(list_ports=fake_mod)))
    monkeypatch.setitem(sys.modules, "serial.tools", SimpleNamespace(list_ports=fake_mod))
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", fake_mod)

    ports = list_candidate_ports()
    assert "/dev/ttyS0" not in ports
    assert "/dev/ttyUSB0" in ports
    assert "/dev/ttyACM0" in ports


def _engine(name: str, timeout_s: float = 1.0) -> TransactionEngine:
    transport = FakeTransport.from_fixture_dir(FIXTURES / name)
    return TransactionEngine(
        transport,
        timeout_s=timeout_s,
        prompted_idle_s=0.05,
        prompted=True,
    )


def test_gate_a_required():
    result = run_discover(_engine("discover_ready_off"), gate_a_pass=False)
    assert not result.ready
    assert result.state == "error"
    assert "Gate A" in result.errors[0]


def test_ready_when_source_already_off():
    result = run_discover(_engine("discover_ready_off"), gate_a_pass=True)
    assert result.ready, result.errors
    assert result.state == "ready"
    assert result.first_power_on is False
    assert result.lamp_disabled is False
    assert result.es_position == 1
    assert result.status_model == "55"
    assert not result.job_running
    commands = [t["command"] for t in result.transactions]
    assert commands == ["$ST", "$ES", "$ES 1", "$ES"]


def test_first_power_on_disables_xe_source():
    result = run_discover(_engine("discover_first_power_on"), gate_a_pass=True)
    assert result.ready, result.errors
    assert result.state == "ready"
    assert result.first_power_on is True
    assert result.lamp_disabled is True
    assert result.es_position_initial == 0
    assert result.es_position == 1
    commands = [t["command"] for t in result.transactions]
    assert commands == ["$ST", "$ES", "$ES 1", "$ES"]


def test_busy_leaves_shutter_alone():
    result = run_discover(_engine("discover_busy"), gate_a_pass=True)
    assert not result.ready
    assert result.state == "busy"
    assert result.job_running is True
    assert any("0110" in e for e in result.errors)
    assert result.es_position is None
    commands = [t["command"] for t in result.transactions]
    assert commands == ["$ST"]


def test_read_only_probe_reports_xe_on_without_forcing_off():
    result = run_discover(
        _engine("discover_first_power_on"),
        gate_a_pass=True,
        force_idle_source_off=False,
    )
    assert result.ready, result.errors
    assert result.state == "ready"
    assert result.first_power_on is True
    assert result.lamp_disabled is False
    assert result.es_position == 0
    commands = [t["command"] for t in result.transactions]
    assert commands == ["$ST", "$ES"]
    assert "$ES 1" not in commands


def test_boot_poll_then_ready():
    sleeps: list[float] = []

    result = run_discover(
        _engine("discover_boot_then_ready", timeout_s=0.2),
        gate_a_pass=True,
        boot_wait_s=2.0,
        boot_poll_s=0.01,
        sleep=sleeps.append,
    )
    assert result.ready, result.errors
    assert result.state == "ready"
    assert result.boot_attempts >= 2
    assert sleeps  # waited between boot polls
    assert result.first_power_on is False
    assert result.lamp_disabled is False


def test_boot_window_exhausted():
    result = run_discover(
        _engine("discover_boot_timeout", timeout_s=0.15),
        gate_a_pass=True,
        boot_wait_s=0.2,
        boot_poll_s=0.01,
        sleep=lambda _s: None,
    )
    assert not result.ready
    assert result.state == "booting"
    assert result.boot_attempts >= 1
    assert any("boot window" in e for e in result.errors)
