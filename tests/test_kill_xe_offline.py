"""Offline kill_xe CLI checks against synthetic fixtures."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = REPO_ROOT / "scripts" / "kill_xe.py"


def _run(fixture: str, log_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--fixture-dir",
            str(FIXTURES / fixture),
            "--log-dir",
            str(log_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_kill_xe_when_source_on(tmp_path: Path):
    proc = _run("discover_first_power_on", tmp_path)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["ok"] is True
    assert summary["was_on"] is True
    assert summary["es_after"] == 1
    assert "Xe OFF (was ON)" in proc.stderr


def test_kill_xe_when_already_off(tmp_path: Path):
    proc = _run("discover_ready_off", tmp_path)
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["ok"] is True
    assert summary["was_on"] is False
    assert summary["es_after"] == 1
    assert "Xe already OFF" in proc.stderr
