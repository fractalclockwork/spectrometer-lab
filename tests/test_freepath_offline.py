"""Offline Stage-3 free-path spectrum validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ls55.freepath import run_freepath
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _engine(name: str) -> TransactionEngine:
    transport = FakeTransport.from_fixture_dir(FIXTURES / name)
    return TransactionEngine(
        transport,
        timeout_s=2.0,
        prompted_idle_s=0.05,
        prompted=True,
    )


def test_freepath_requires_gates():
    result = run_freepath(
        _engine("freepath_happy"),
        stage2_pass=False,
        compartment_closed=True,
    )
    assert not result.passed
    assert "Stage 2" in result.errors[0]

    result = run_freepath(
        _engine("freepath_happy"),
        stage2_pass=True,
        compartment_closed=False,
    )
    assert not result.passed
    assert "compartment" in result.errors[0]


def test_freepath_happy_pass():
    result = run_freepath(
        _engine("freepath_happy"),
        stage2_pass=True,
        compartment_closed=True,
        scan_timeout_s=2.0,
        motion_timeout_s=2.0,
    )
    assert result.passed, result.errors
    assert result.dark is not None
    assert result.empty_on is not None
    assert len(result.dark.intensity) == 12
    assert len(result.empty_on.intensity) == 12
    assert result.dark.intensity[0] == 1
    assert result.empty_on.intensity[0] == 100
    assert result.dark.wavelength_nm[0] == 400.0
    assert result.es_after == 1
    assert result.restored


def test_cli_freepath_fixture(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    log_dir = tmp_path / "logs"
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_freepath_serial.py"),
            "--fixture-dir",
            str(FIXTURES / "freepath_happy"),
            "--stage2-pass",
            "--compartment-closed",
            "--log-dir",
            str(log_dir),
            "--timeout",
            "2.0",
            "--motion-timeout",
            "2.0",
            "--scan-timeout",
            "2.0",
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    summaries = list(log_dir.glob("freepath-*.json"))
    assert summaries
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["csv"]
    assert summary["png"]
    assert Path(summary["csv"]).is_file()
    assert Path(summary["png"]).is_file()
