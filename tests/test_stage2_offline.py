"""Offline Stage-2 / Gate C validation."""

from __future__ import annotations

from pathlib import Path

from ls55.stage2 import run_stage2
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _engine(name: str, timeout_s: float = 2.0) -> TransactionEngine:
    transport = FakeTransport.from_fixture_dir(FIXTURES / name)
    return TransactionEngine(
        transport,
        timeout_s=timeout_s,
        prompted_idle_s=0.05,
        prompted=True,
    )


def test_stage1_required():
    result = run_stage2(_engine("stage2_happy"), stage1_pass=False)
    assert not result.passed
    assert "Stage 1" in result.errors[0]


def test_stage2_happy_pass():
    result = run_stage2(
        _engine("stage2_happy"),
        stage1_pass=True,
        motion_timeout_s=2.0,
    )
    assert result.passed, result.errors
    assert result.es_position == 1
    assert result.gm_readback is not None
    assert "350.0" in result.gm_readback
    assert result.sx_readback is not None
    assert result.sm_readback is not None
    assert result.rd_data is not None
    assert result.restored


def test_cli_stage2_fixture(tmp_path):
    import json
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    log_dir = tmp_path / "logs"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_stage2_serial.py"),
            "--fixture-dir",
            str(FIXTURES / "stage2_happy"),
            "--stage1-pass",
            "--log-dir",
            str(log_dir),
            "--timeout",
            "2.0",
            "--motion-timeout",
            "2.0",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summaries = list(log_dir.glob("stage2-*.json"))
    assert summaries
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["passed"] is True
