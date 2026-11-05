"""Offline tonic-water blank load, peak annotate, and CLI smoke."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

from ls55.plot_spectrum import (
    annotate_guide_peaks,
    load_blank_intensity_csv,
    plot_annotated_emission,
    subtract_blank,
    write_corrected_csv,
    write_freepath_csv,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO = Path(__file__).resolve().parents[1]


def test_load_blank_intensity_freepath_and_sample_on(tmp_path):
    freepath = tmp_path / "blank-fp.csv"
    write_freepath_csv(
        freepath,
        wavelength_nm=[400.0, 402.0, 404.0],
        dark=[0, 0, 0],
        empty_on=[10.0, 20.0, 30.0],
    )
    wl, intensity = load_blank_intensity_csv(freepath)
    assert wl == [400.0, 402.0, 404.0]
    assert intensity == [10.0, 20.0, 30.0]

    corrected = tmp_path / "blank-corr.csv"
    write_corrected_csv(
        corrected,
        wavelength_nm=[400.0, 402.0],
        sample_on=[11.0, 22.0],
        blank=[0.0, 0.0],
        corrected=[11.0, 22.0],
    )
    wl2, intensity2 = load_blank_intensity_csv(corrected)
    assert wl2 == [400.0, 402.0]
    assert intensity2 == [11.0, 22.0]


def test_load_blank_intensity_requires_intensity_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("wavelength_nm,dark\n400,0\n", encoding="utf-8")
    try:
        load_blank_intensity_csv(bad)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "empty_on or sample_on" in str(exc)


def test_annotate_quinine_guide(tmp_path):
    wl = [float(x) for x in range(400, 551, 2)]
    corrected = [
        8000.0 * math.exp(-((w - 450.0) ** 2) / (2 * 18.0**2)) for w in wl
    ]
    peaks = annotate_guide_peaks(
        wl,
        corrected,
        guide_nm=(450.0,),
        guide_labels=("Quinine ~450",),
        half_window_nm=25.0,
    )
    guide = next(p for p in peaks if p.guide_nm == 450.0)
    assert abs(guide.observed_nm - 450.0) <= 2.0
    assert guide.observed_intensity > 1000.0

    png = tmp_path / "tonic.png"
    plot_annotated_emission(
        png,
        wavelength_nm=wl,
        corrected=corrected,
        peaks=peaks,
        title="Tonic water 1:80 (blank-subtracted)",
    )
    assert png.is_file() and png.stat().st_size > 0


def test_cli_tonic_water_fixture(tmp_path):
    log_dir = tmp_path / "logs"
    blank_path = tmp_path / "blank.csv"
    blank_wl = [400.0 + 2.0 * i for i in range(76)]
    write_freepath_csv(
        blank_path,
        wavelength_nm=blank_wl,
        dark=[0] * len(blank_wl),
        empty_on=[10.0 + i for i in range(len(blank_wl))],
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "run_tonic_water_serial.py"),
            "--fixture-dir",
            str(FIXTURES / "freepath_happy"),
            "--stage2-pass",
            "--sample-loaded",
            "--blank",
            str(blank_path),
            "--log-dir",
            str(log_dir),
            "--dilution",
            "1:80",
            # freepath_happy only emits ~12 points from Em 400 nm; aim guide
            # inside that short window for offline smoke.
            "--guide",
            "410",
            "--half-window",
            "15",
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
    summaries = list(log_dir.glob("tonic-water-*.json"))
    assert summaries
    summary = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["experiment"] == "tonic-water"
    assert summary["dilution"] == "1:80"
    assert summary["replicate_kind"] == "sanity"
    assert summary["series_id"] == "fixture-test"
    assert summary["clipped"] is False
    assert summary["csv"]
    assert summary["png"]
    assert summary["peaks"]
    assert summary["peak"] is not None
    assert Path(summary["csv"]).is_file()
    assert Path(summary["png"]).is_file()


def test_summarize_tonic_water(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    for i, kind in enumerate(("sanity", "technical", "technical", "reseat")):
        payload = {
            "experiment": "tonic-water",
            "series_id": "demo",
            "replicate_kind": kind,
            "dilution": "1:80",
            "passed": True,
            "clipped": False,
            "settings": {
                "ex_nm": 350.0,
                "em_lo": 400.0,
                "em_hi": 550.0,
                "interval_nm": 2.0,
                "speed": 120,
                "slit_nm": 5.0,
            },
            "peak": {
                "observed_nm": 448.0 + 0.5 * i,
                "observed_intensity": 20000.0 + 100 * i,
                "delta_nm": (448.0 + 0.5 * i) - 450.0,
                "guide_nm": 450.0,
            },
            "peaks": [
                {
                    "label": "Quinine ~450",
                    "guide_nm": 450.0,
                    "observed_nm": 448.0 + 0.5 * i,
                    "observed_intensity": 20000.0 + 100 * i,
                }
            ],
        }
        (log_dir / f"tonic-water-20260101-00000{i}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    (log_dir / "tonic-water-other.json").write_text(
        json.dumps(
            {
                "experiment": "other",
                "series_id": "demo",
                "replicate_kind": "technical",
            }
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "summarize_tonic_water.py"),
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
    assert summary["dilutions"] == ["1:80"]
    assert summary["by_replicate_kind"]["technical"]["n"] == 2
    assert summary["by_replicate_kind"]["reseat"]["n"] == 1
    assert summary["gate_technical_plus_reseat"]["n"] == 3
    assert summary["n_skipped"] == 1


def test_subtract_with_blank_loader(tmp_path):
    blank_path = tmp_path / "blank.csv"
    write_freepath_csv(
        blank_path,
        wavelength_nm=[440.0, 450.0, 460.0],
        dark=[0, 0, 0],
        empty_on=[100.0, 110.0, 120.0],
    )
    blank_wl, blank_i = load_blank_intensity_csv(blank_path)
    spectrum = subtract_blank(
        [440.0, 450.0, 460.0],
        [500.0, 1110.0, 620.0],
        blank_wl,
        blank_i,
    )
    assert spectrum.corrected == [400.0, 1000.0, 500.0]
