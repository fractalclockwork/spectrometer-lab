"""Offline ensure_source_off checks."""

from __future__ import annotations

from pathlib import Path

from ls55.source import SOURCE_OFF, ensure_source_off
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _engine(name: str) -> TransactionEngine:
    transport = FakeTransport.from_fixture_dir(FIXTURES / name)
    return TransactionEngine(
        transport,
        timeout_s=1.0,
        prompted_idle_s=0.05,
        prompted=True,
    )


def test_ensure_off_when_already_off():
    result = ensure_source_off(_engine("discover_ready_off"))
    assert result.ok, result.errors
    assert result.was_on is False
    assert result.es_before == SOURCE_OFF
    assert result.es_after == SOURCE_OFF
    assert result.commanded is True


def test_ensure_off_when_source_on():
    result = ensure_source_off(_engine("discover_first_power_on"))
    assert result.ok, result.errors
    assert result.was_on is True
    assert result.es_before == 0
    assert result.es_after == SOURCE_OFF
