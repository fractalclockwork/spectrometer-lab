"""Offline identity-dump harness tests."""

from pathlib import Path

from ls55.identity import run_identity_dump
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_identity_happy_path():
    transport = FakeTransport.from_fixture_dir(FIXTURES / "identity_happy")
    engine = TransactionEngine(transport, timeout_s=2.0, prompted=True)
    result = run_identity_dump(engine, gate_a_pass=True, compartment_closed=True)
    assert result.ok
    assert result.es_position == 1
    assert result.me_code == "0000"
    assert result.status is not None
    assert result.status["model"] == "55"
    assert result.status["revision"] == "F1"
    assert result.status["speed"] == 480
    assert result.status["response"] == 19
    assert result.status["flashcount"] == 1
    assert result.accessories is not None
    assert "excitation_polarizer" in result.accessories["fitted"]
    assert "emission_polarizer" in result.accessories["fitted"]
    assert result.readbacks["$SN"]["data"] == ["1234567"]
    assert result.readbacks["$HZ"]["data"] == ["60"]
    assert result.readbacks["$PV"]["data"] == ["650A"]
    assert result.readbacks["$CX"]["data"] == ["1"]
    assert result.readbacks["$TP"]["final_code"] == "0100"
    assert result.readbacks["$PH"]["data"] == ["0"]


def test_identity_refuses_without_gate():
    transport = FakeTransport.from_fixture_dir(FIXTURES / "identity_happy")
    engine = TransactionEngine(transport, timeout_s=2.0, prompted=True)
    result = run_identity_dump(engine, gate_a_pass=False, compartment_closed=True)
    assert not result.ok
    assert any("Gate A" in e for e in result.errors)
