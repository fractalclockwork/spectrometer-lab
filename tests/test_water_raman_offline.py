"""Offline water-Raman blank subtract, SNR, peak annotate, and CLI smoke."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

from ls55.plot_spectrum import (
    annotate_guide_peaks,
    compute_raman_snr,
    load_freepath_csv,
    plot_annotated_emission,
    subtract_blank,
    write_corrected_csv,
    write_freepath_csv,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]


def test_load_and_subtract_blank(tmp_path):
    blank_path = tmp_path / "blank.csv"
    write_freepath_csv(
        blank_path,
        wavelength_nm=[380.0, 382.0, 384.0, 386.0],
        dark=[0, 0, 0, 0],
        empty_on=[100.0, 110.0, 120.0, 130.0],
    )
    wl, dark, empty = load_freepath_csv(blank_path)
    assert wl == [380.0, 382.0, 384.0, 386.0]
    assert dark == [0.0, 0.0, 0.0, 0.0]
    assert empty == [100.0, 110.0, 120.0, 130.0]

    spectrum = subtract_blank(
        [382.0, 384.0, 386.0, 388.0],
        [210.0, 320.0, 430.0, 999.0],
        wl,
        empty,
    )
    assert spectrum.wavelength_nm == [382.0, 384.0, 386.0]
    assert spectrum.sample_on == [210.0, 320.0, 430.0]
    assert spectrum.blank == [110.0, 120.0, 130.0]
    assert spectrum.corrected == [100.0, 200.0, 300.0]


def test_subtract_blank_requires_overlap():
    try:
        subtract_blank([400.0], [1.0], [500.0], [2.0])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "overlapping" in str(exc)


def test_annotate_guide_and_snr(tmp_path):
    wl = [float(x) for x in range(380, 421, 2)]
    corrected = []
    for w in wl:
        v = 5000.0 * math.exp(-((w - 397.0) ** 2) / (2 * 4.0**2))
        if w >= 410.0:
            v += 20.0  # quiet-band floor with small scatter via later noise test
        corrected.append(v)
    # Add deterministic noise in 410–420 for non-zero RMS.
    for i, w in enumerate(wl):
        if 410.0 <= w <= 420.0:
            corrected[i] = 20.0 + (5.0 if int(w) % 4 == 0 else -5.0)

    peaks = annotate_guide_peaks(
        wl,
        corrected,
        guide_nm=(397.0,),
        guide_labels=("Water Raman ~397",),
    )
    assert any(p.guide_nm == 397.0 for p in peaks)
    max_peak = next(p for p in peaks if "max" in p.label.lower())
    assert abs(max_peak.observed_nm - 397.0) <= 2.0

    snr = compute_raman_snr(
        wl,
        corrected,
        guide_nm=397.0,
        noise_lo_nm=410.0,
        noise_hi_nm=420.0,
    )
    assert abs(snr.peak_nm - 397.0) <= 2.0
    assert snr.n_noise_points >= 2
    assert snr.noise_rms > 0.0
    assert snr.snr is not None and snr.snr > 1.0

    png = tmp_path / "annotated.png"
    plot_annotated_emission(
        png,
        wavelength_nm=wl,
        corrected=corrected,
        peaks=peaks,
        title="Distilled water Raman (blank-subtracted)",
        blank_path=tmp_path / "blank.csv",
    )
    assert png.is_file() and png.stat().st_size > 0

    csv_path = tmp_path / "corrected.csv"
    write_corrected_csv(
        csv_path,
        wavelength_nm=wl,
        sample_on=[c + 50 for c in corrected],
        blank=[50.0] * len(wl),
        corrected=corrected,
    )
    assert csv_path.read_text(encoding="utf-8").startswith(
        "wavelength_nm,sample_on,blank,corrected\n"
    )


def test_cli_water_raman_fixture(tmp_path):
    log_dir = tmp_path / "logs"
    # freepath_happy fixture covers Em 400–550; override CLI Em to match.
    blank_path = tmp_path / "blank.csv"
    blank_wl = [400.0 + 2.0 * i for i in range(12)]
    write_freepath_csv(
        blank_path,
        wavelength_nm=blank_wl,
        dark=[0] * 12,
        empty_on=[10.0 + i for i in range(12)],
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "run_water_raman_serial.py"),
            "--fixture-dir",
            str(FIXTURES / "freepath_happy"),
            "--stage2-pass",
            "--sample-loaded",
            "--blank",
            str(blank_path),
            "--log-dir",
            str(log_dir),
            "--em-lo",
            "400",
            "--em-hi",
            "550",
            "--noise-lo",
            "410",
            "--noise-hi",
            "420",
            "--replicate-kind",
            "sanity",
            "--series-id",
            "fixture-test",
            "--timeout",
            "2.0",
            "--motion-timeout",
            "2.0",
            "--scan-timeout",
            "2.0",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    summaries = list(log_dir.glob("water-raman-*.json"))
    assert summaries
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["experiment"] == "water-raman"
    assert summary["sample"] == "distilled water"
    assert summary["replicate_kind"] == "sanity"
    assert summary["series_id"] == "fixture-test"
    assert summary["csv"]
    assert summary["png"]
    assert summary["peaks"]
    assert summary["snr"] is not None
    assert Path(summary["csv"]).is_file()
    assert Path(summary["png"]).is_file()


def test_summarize_water_raman(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for i, kind in enumerate(("sanity", "technical", "technical", "reseat")):
        payload = {
            "experiment": "water-raman",
            "series_id": "demo",
            "replicate_kind": kind,
            "passed": True,
            "settings": {
                "ex_nm": 350.0,
                "em_lo": 380.0,
                "em_hi": 420.0,
                "interval_nm": 2.0,
                "speed": 120,
                "slit_nm": 10.0,
            },
            "peaks": [
                {
                    "label": "Water Raman ~397",
                    "guide_nm": 397.0,
                    "observed_nm": 398.0 + 0.5 * i,
                    "observed_intensity": 1000.0 + 10 * i,
                }
            ],
            "snr": {
                "peak_nm": 398.0 + 0.5 * i,
                "peak_intensity": 1000.0 + 10 * i,
                "noise_rms": 10.0,
                "snr": 100.0 + i,
                "noise_lo_nm": 410.0,
                "noise_hi_nm": 420.0,
                "n_noise_points": 5,
            },
        }
        (log_dir / f"water-raman-20260101-00000{i}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    # Invalid leftover experiment must be ignored.
    (log_dir / "water-raman-tap.json").write_text(
        json.dumps(
            {
                "experiment": "tap-water-raman",
                "series_id": "demo",
                "replicate_kind": "technical",
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "summarize_water_raman.py"),
            "--series-id",
            "demo",
            "--log-dir",
            str(log_dir),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + "\n" + proc.stdout
    out = log_dir / "demo-summary.json"
    assert out.is_file()
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["n_matched"] == 4
    assert summary["by_replicate_kind"]["technical"]["n"] == 2
    assert summary["by_replicate_kind"]["reseat"]["n"] == 1
    assert summary["calibration_technical_plus_reseat"]["n"] == 3
    assert summary["n_skipped"] == 1
