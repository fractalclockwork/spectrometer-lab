"""Offline $ES on/off cycle."""

from __future__ import annotations

from pathlib import Path

from ls55.es_cycle import run_es_cycle
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_es_cycle_requires_compartment_flag():
    transport = FakeTransport.from_fixture_dir(FIXTURES / "es_cycle_happy")
    engine = TransactionEngine(transport, timeout_s=2.0, prompted_idle_s=0.05)
    result = run_es_cycle(engine, compartment_closed=False)
    assert not result.passed
    assert "compartment" in result.errors[0]


def test_es_cycle_happy():
    transport = FakeTransport.from_fixture_dir(FIXTURES / "es_cycle_happy")
    engine = TransactionEngine(transport, timeout_s=2.0, prompted_idle_s=0.05)
    result = run_es_cycle(engine, compartment_closed=True, on_dwell_s=0.0)
    assert result.passed, result.errors
    assert result.before == 1
    assert result.after_on == 0
    assert result.after_off == 1
