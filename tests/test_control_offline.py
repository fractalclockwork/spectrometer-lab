"""Offline tests for Status/Setup, Single Read, streaming, abort flag."""

from __future__ import annotations

from pathlib import Path

from ls55.acquire import ScanConfig, run_spectrum_scan
from ls55.control import OpticalSetup, run_single_read
from ls55.protocol import Record
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


def test_optical_setup_validate():
    bad = OpticalSetup(ex_nm=50.0, em_nm=450.0)
    errs = bad.validate()
    assert any("ex_nm" in e for e in errs)

    good = OpticalSetup(ex_nm=350.0, em_nm=450.0, ex_slit=5.0, em_slit=5.0)
    assert good.validate() == []


def test_single_read_happy():
    result = run_single_read(
        _engine("single_read_happy"),
        ex_nm=350.0,
        em_nm=450.0,
        integration_s=1.0,
        dark_correct=True,
        motion_timeout_s=2.0,
    )
    assert result.ok, result.errors
    assert result.dark_intensity == 2.0
    assert result.intensity == 1234.0
    assert result.corrected == 1232.0
    assert result.es_after == 1
    assert not result.clipped


def test_spectrum_scan_streams_points():
    points: list[tuple[float, int, str]] = []
    result = run_spectrum_scan(
        _engine("scan_happy"),
        ScanConfig(
            mx=1,
            ex_nm=350.0,
            em_lo=400.0,
            em_hi=550.0,
            interval_nm=2.0,
            speed=120,
            ex_slit=5.0,
            em_slit=5.0,
            include_dark=True,
        ),
        compartment_closed=True,
        motion_timeout_s=2.0,
        scan_timeout_s=2.0,
        on_point=lambda wl, inten, arm: points.append((wl, inten, arm)),
    )
    assert result.passed, result.errors
    assert result.dark is not None and result.sample is not None
    assert len(result.dark.intensity) == 12
    assert len(result.sample.intensity) == 12
    assert any(arm == "dark" for _, _, arm in points)
    assert any(arm.startswith("sample") for _, _, arm in points)
    assert points[0][0] == 400.0
    assert result.es_after == 1


def test_on_record_callback_and_abort_flag():
    engine = _engine("scan_happy")
    seen: list[str] = []

    def on_record(record: Record, txn) -> None:
        seen.append(record.code or (record.data or "")[:20])
        if len(seen) == 3:
            engine.request_abort()

    # Short status-like transaction still works with on_record.
    st = engine.transact("$AB", on_record=on_record)
    assert st.final_code in {"0002", "0000", "0099"}
    assert seen
    engine.clear_abort()
    assert not engine._abort_pending()
