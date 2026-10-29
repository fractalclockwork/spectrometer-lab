"""Offline Stage-1 validation against synthetic fixtures."""

from __future__ import annotations

from pathlib import Path

from ls55.stage1 import run_stage1
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _engine(name: str, timeout_s: float = 1.0) -> TransactionEngine:
    transport = FakeTransport.from_fixture_dir(FIXTURES / name)
    return TransactionEngine(
        transport,
        timeout_s=timeout_s,
        prompted_idle_s=0.05,
        prompted=True,
    )


def test_gate_a_required():
    result = run_stage1(_engine("happy_path"), gate_a_pass=False)
    assert not result.passed
    assert "Gate A" in result.errors[0]


def test_happy_path_pass():
    result = run_stage1(_engine("happy_path"), gate_a_pass=True)
    assert result.passed, result.errors
    assert result.status_model == "55"
    assert result.status_revision == "A1"
    assert result.es_position == 1
    assert result.me_code == "0000"
    assert result.af_bits is not None
    assert "$GM" in result.optional_readbacks


def test_live_st_format_with_glitch_prefix():
    """Matches captured DUT: leading 0xb5 on first code, STATUS 55.F1,..."""
    result = run_stage1(_engine("live_st_format"), gate_a_pass=True)
    assert result.passed, result.errors
    assert result.status_model == "55"
    assert result.status_revision == "F1"
    assert result.es_position == 1



def test_fragmented_reads_pass():
    result = run_stage1(_engine("fragmented"), gate_a_pass=True)
    assert result.passed, result.errors
    assert result.status_model == "55"


def test_me_0108_warn_still_pass():
    result = run_stage1(_engine("me_0108"), gate_a_pass=True)
    assert result.passed, result.errors
    assert result.me_code == "0108"
    assert any("0108" in w for w in result.warnings)


def test_me_0106_fail():
    result = run_stage1(
        _engine("me_0106"),
        gate_a_pass=True,
        include_optional_readbacks=False,
    )
    assert not result.passed
    assert any("0106" in e for e in result.errors)


def test_timeout_fail():
    result = run_stage1(
        _engine("timeout", timeout_s=0.3),
        gate_a_pass=True,
        include_optional_readbacks=False,
    )
    assert not result.passed
    assert any("timeout" in e for e in result.errors)


def test_busy_fail():
    result = run_stage1(
        _engine("busy"),
        gate_a_pass=True,
        include_optional_readbacks=False,
    )
    assert not result.passed
    assert any("0110" in e for e in result.errors)


def test_bad_model_fail():
    result = run_stage1(
        _engine("bad_model"),
        gate_a_pass=True,
        include_optional_readbacks=False,
    )
    assert not result.passed
    assert any("55" in e for e in result.errors)


def test_es_still_on_fail():
    result = run_stage1(
        _engine("es_still_on"),
        gate_a_pass=True,
        include_optional_readbacks=False,
    )
    assert not result.passed
    assert any("position 1" in e for e in result.errors)


def test_cli_fixture_happy(tmp_path):
    import json
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    log_dir = tmp_path / "logs"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_stage1_serial.py"),
            "--fixture-dir",
            str(FIXTURES / "happy_path"),
            "--gate-a-pass",
            "--log-dir",
            str(log_dir),
            "--timeout",
            "1.0",
            "--baud",
            "9600",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summaries = list(log_dir.glob("stage1-*.json"))
    assert summaries
    assert list(log_dir.glob("stage1-*.log"))
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary.get("baud") == 9600
    assert summary.get("passed") is True
