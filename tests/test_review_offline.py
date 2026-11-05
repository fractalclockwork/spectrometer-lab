"""Offline WinLab Data Calculator / review math tests."""

from __future__ import annotations

import math

from ls55.review import (
    blank_settings_compatible,
    compute_transmission_absorbance,
    compute_wing_continuum_residual,
    recompute_run_review,
)
from ls55.sidecar import build_run_sidecar


def test_wing_continuum_recovers_peak_on_slope():
    # Sloping continuum + Gaussian-like bump near 397 nm.
    wl = [380.0 + i for i in range(0, 41)]  # 380–420
    continuum = [1000.0 + 40.0 * (w - 380.0) for w in wl]
    intensity = []
    for w, c in zip(wl, continuum):
        bump = 2500.0 * math.exp(-0.5 * ((w - 397.0) / 3.0) ** 2)
        intensity.append(c + bump)

    wing = compute_wing_continuum_residual(
        wl,
        intensity,
        left_wing=(380.0, 386.0),
        right_wing=(410.0, 420.0),
        peak_search=(397.0, 8.0),
    )
    assert wing.residual_peak_nm is not None
    assert abs(wing.residual_peak_nm - 397.0) <= 1.0
    assert wing.residual_peak_delta_i is not None
    assert wing.residual_peak_delta_i > 2000.0


def test_recompute_dual_snr_and_blank_match():
    wl = [400.0 + 2.0 * i for i in range(76)]
    blank = [50.0 + 0.1 * i for i in range(76)]
    sample = [b + 1000.0 * math.exp(-0.5 * ((w - 450.0) / 12.0) ** 2) for w, b in zip(wl, blank)]

    rev = recompute_run_review(
        wavelength_nm=wl,
        sample_on=sample,
        blank_wl=wl,
        blank_i=blank,
        guide_nm=450.0,
        half_window_nm=25.0,
        noise_lo_nm=520.0,
        noise_hi_nm=550.0,
        left_wing=(400.0, 410.0),
        right_wing=(520.0, 550.0),
        sample_settings={"ex_nm": 350.0, "slit_nm": 5.0, "speed": 120, "interval_nm": 2.0},
        blank_settings={"ex_nm": 350.0, "slit_nm": 5.0, "speed": 120, "interval_nm": 2.0},
    )
    assert rev.blank_settings_match is True
    assert rev.peak_nm is not None
    assert abs(rev.peak_nm - 450.0) <= 2.0
    assert rev.absolute_snr is not None and rev.absolute_snr > 10.0
    assert rev.contrast_snr is not None and rev.contrast_snr > 5.0
    assert len(rev.residual) == len(rev.wavelength_nm)


def test_blank_settings_mismatch():
    ok, notes = blank_settings_compatible(
        {"ex_nm": 350.0, "slit_nm": 5.0, "speed": 120, "interval_nm": 2.0},
        {"ex_nm": 350.0, "slit_nm": 10.0, "speed": 120, "interval_nm": 2.0},
    )
    assert ok is False
    assert any("slit_nm" in n for n in notes)


def test_transmission_absorbance():
    wl = [400.0, 450.0, 500.0]
    i0 = [1000.0, 1000.0, 1000.0]
    i = [100.0, 10.0, 1.0]
    ta = compute_transmission_absorbance(wl, i, wl, i0)
    assert abs(ta.transmittance[0] - 0.1) < 1e-9
    assert abs(ta.absorbance[0] - 1.0) < 1e-9
    assert abs(ta.absorbance[1] - 2.0) < 1e-9


def test_sidecar_builder(tmp_path):
    side = build_run_sidecar(
        experiment="tonic-water",
        method_name="tonic_quinine",
        series_id="test",
        replicate_kind="technical",
        passed=True,
        optics={"ex_nm": 350.0, "em_lo": 400.0},
        repo_root=tmp_path,
    )
    path = side.write_json(tmp_path / "run.json")
    assert path.is_file()
    data = side.to_dict()
    assert data["provenance"]["instrument_model"] == "55"
    assert data["ls55_optics"]["ex_nm"] == 350.0
    assert data["optical_path_config"]["geometry"] == "right_angle_4w"


def test_discover_includes_dashboard_scans(tmp_path):
    from ls55.review import discover_blank_candidates, discover_logged_runs

    scans = tmp_path / "dashboard" / "scans"
    scans.mkdir(parents=True)
    csv_path = scans / "dashboard-scan-demo.csv"
    json_path = scans / "dashboard-scan-demo.json"
    csv_path.write_text(
        "wavelength_nm,sample_on,blank,corrected\n400,100,10,90\n402,110,10,100\n",
        encoding="utf-8",
    )
    json_path.write_text(
        '{"experiment":"dashboard-scan","replicate_kind":"sanity","passed":true,'
        '"artifacts":{"csv":"%s"}}' % csv_path,
        encoding="utf-8",
    )
    runs = discover_logged_runs(tmp_path)
    assert any(r["run_id"] == "dashboard-scan-demo" for r in runs)
    blanks = discover_blank_candidates(tmp_path)
    assert any(b["name"] == "dashboard-scan-demo.csv" for b in blanks)
