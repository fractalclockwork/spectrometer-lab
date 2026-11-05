"""WinLab Viewing / Data Calculator: blank swap, wing residual, dual SNR."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from ls55.plot_spectrum import (
    BlankSubtractedSpectrum,
    RamanSnrResult,
    compute_raman_snr,
    find_local_max_near,
    load_blank_intensity_csv,
    subtract_blank,
)

CLIP_THRESHOLD = 900_000.0


@dataclass(frozen=True)
class WingContinuumResult:
    wavelength_nm: list[float]
    intensity: list[float]
    continuum_fit: list[float]
    residual: list[float]
    left_wing: tuple[float, float]
    right_wing: tuple[float, float]
    residual_peak_nm: Optional[float]
    residual_peak_delta_i: Optional[float]
    n_fit_points: int
    slope: float
    intercept: float


@dataclass(frozen=True)
class TransmissionAbsorbanceResult:
    wavelength_nm: list[float]
    transmittance: list[float]
    absorbance: list[float]
    sample_on: list[float]
    reference: list[float]


@dataclass
class RunReviewResult:
    wavelength_nm: list[float]
    sample_on: list[float]
    blank: list[float]
    corrected: list[float]
    continuum_fit: list[float] = field(default_factory=list)
    residual: list[float] = field(default_factory=list)
    peak_nm: Optional[float] = None
    peak_intensity: Optional[float] = None
    delta_nm: Optional[float] = None
    absolute_snr: Optional[float] = None
    contrast_snr: Optional[float] = None
    residual_peak_nm: Optional[float] = None
    residual_peak_delta_i: Optional[float] = None
    clipped: bool = False
    blank_settings_match: Optional[bool] = None
    blank_match_notes: list[str] = field(default_factory=list)
    transmittance: list[float] = field(default_factory=list)
    absorbance: list[float] = field(default_factory=list)
    mode: str = "fluorescence"  # fluorescence | transmission

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _linear_fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        raise ValueError("need at least 2 points for linear wing fit")
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom <= 0:
        return 0.0, mean_y
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    return slope, intercept


def compute_wing_continuum_residual(
    wavelength_nm: Sequence[float],
    intensity: Sequence[float],
    *,
    left_wing: tuple[float, float] = (380.0, 386.0),
    right_wing: tuple[float, float] = (410.0, 420.0),
    peak_search: Optional[tuple[float, float]] = None,
) -> WingContinuumResult:
    """
    Fit a linear continuum across two wing windows and return residual ΔI.

    ``peak_search`` is ``(center_nm, half_window_nm)`` for residual peak pick.
    """
    wl = [float(w) for w in wavelength_nm]
    inten = [float(v) for v in intensity]
    if len(wl) != len(inten) or not wl:
        raise ValueError("wavelength_nm and intensity must be same non-empty length")

    left_lo, left_hi = float(left_wing[0]), float(left_wing[1])
    right_lo, right_hi = float(right_wing[0]), float(right_wing[1])
    if left_hi < left_lo or right_hi < right_lo:
        raise ValueError("wing windows must have hi >= lo")

    fit_x: list[float] = []
    fit_y: list[float] = []
    for w, v in zip(wl, inten):
        if left_lo <= w <= left_hi or right_lo <= w <= right_hi:
            fit_x.append(w)
            fit_y.append(v)
    if len(fit_x) < 2:
        raise ValueError(
            f"need ≥2 points in wings {left_wing} / {right_wing}; got {len(fit_x)}"
        )

    slope, intercept = _linear_fit(fit_x, fit_y)
    continuum = [slope * w + intercept for w in wl]
    residual = [v - c for v, c in zip(inten, continuum)]

    residual_peak_nm: Optional[float] = None
    residual_peak_delta_i: Optional[float] = None
    if peak_search is not None:
        center, half = float(peak_search[0]), float(peak_search[1])
        found = find_local_max_near(wl, residual, center, half_window_nm=half)
        if found is not None:
            residual_peak_nm, residual_peak_delta_i = found
    else:
        # Global residual max (useful when no guide supplied).
        idx = max(range(len(residual)), key=lambda i: residual[i])
        residual_peak_nm = wl[idx]
        residual_peak_delta_i = residual[idx]

    return WingContinuumResult(
        wavelength_nm=wl,
        intensity=inten,
        continuum_fit=continuum,
        residual=residual,
        left_wing=(left_lo, left_hi),
        right_wing=(right_lo, right_hi),
        residual_peak_nm=residual_peak_nm,
        residual_peak_delta_i=residual_peak_delta_i,
        n_fit_points=len(fit_x),
        slope=slope,
        intercept=intercept,
    )


def compute_transmission_absorbance(
    sample_wl: Sequence[float],
    sample_i: Sequence[float],
    ref_wl: Sequence[float],
    ref_i: Sequence[float],
) -> TransmissionAbsorbanceResult:
    """Compute T = I/I0 and A = -log10(I/I0) on overlapping wavelengths."""
    ref_map = {round(float(w), 1): float(v) for w, v in zip(ref_wl, ref_i)}
    wavelength_nm: list[float] = []
    sample_on: list[float] = []
    reference: list[float] = []
    transmittance: list[float] = []
    absorbance: list[float] = []
    for w, v in zip(sample_wl, sample_i):
        key = round(float(w), 1)
        if key not in ref_map:
            continue
        i0 = ref_map[key]
        i = float(v)
        wavelength_nm.append(key)
        sample_on.append(i)
        reference.append(i0)
        if i0 <= 0:
            t = float("nan")
            a = float("nan")
        else:
            t = i / i0
            a = -math.log10(t) if t > 0 else float("inf")
        transmittance.append(t)
        absorbance.append(a)
    if not wavelength_nm:
        raise ValueError("no overlapping wavelengths between sample and reference")
    return TransmissionAbsorbanceResult(
        wavelength_nm=wavelength_nm,
        transmittance=transmittance,
        absorbance=absorbance,
        sample_on=sample_on,
        reference=reference,
    )


def compute_contrast_snr(
    residual: Sequence[float],
    wavelength_nm: Sequence[float],
    *,
    residual_peak_delta_i: float,
    noise_lo_nm: float,
    noise_hi_nm: float,
    guide_nm: float,
    half_window_nm: float,
) -> Optional[float]:
    """Contrast SNR = residual_peak_ΔI / RMS(residual in noise window outside peak)."""
    noise_vals: list[float] = []
    for w, v in zip(wavelength_nm, residual):
        wl = float(w)
        if wl < noise_lo_nm or wl > noise_hi_nm:
            continue
        if abs(wl - guide_nm) <= half_window_nm:
            continue
        noise_vals.append(float(v))
    if not noise_vals:
        return None
    mean = sum(noise_vals) / len(noise_vals)
    variance = sum((x - mean) ** 2 for x in noise_vals) / len(noise_vals)
    rms = variance**0.5
    if rms <= 0:
        return None
    return float(residual_peak_delta_i) / rms


def blank_settings_compatible(
    sample_settings: dict[str, Any],
    blank_settings: dict[str, Any],
    *,
    keys: Sequence[str] = ("ex_nm", "slit_nm", "speed", "interval_nm"),
    tol: float = 1e-3,
) -> tuple[bool, list[str]]:
    """Compare optical settings; return (match, notes)."""
    notes: list[str] = []
    ok = True
    for key in keys:
        s = sample_settings.get(key)
        b = blank_settings.get(key)
        if s is None or b is None:
            notes.append(f"{key}: missing (sample={s!r}, blank={b!r})")
            ok = False
            continue
        try:
            if abs(float(s) - float(b)) > tol:
                notes.append(f"{key}: sample={s} blank={b}")
                ok = False
        except (TypeError, ValueError):
            if s != b:
                notes.append(f"{key}: sample={s!r} blank={b!r}")
                ok = False
    return ok, notes


def recompute_run_review(
    *,
    wavelength_nm: Sequence[float],
    sample_on: Sequence[float],
    blank_wl: Optional[Sequence[float]] = None,
    blank_i: Optional[Sequence[float]] = None,
    blank_path: Optional[Path] = None,
    guide_nm: float = 450.0,
    half_window_nm: float = 25.0,
    noise_lo_nm: float = 410.0,
    noise_hi_nm: float = 420.0,
    left_wing: tuple[float, float] = (380.0, 386.0),
    right_wing: tuple[float, float] = (410.0, 420.0),
    mode: str = "fluorescence",
    sample_settings: Optional[dict[str, Any]] = None,
    blank_settings: Optional[dict[str, Any]] = None,
) -> RunReviewResult:
    """
    Non-destructive review: blank subtract (or transmission), wing residual, dual SNR.
    """
    wl = [float(w) for w in wavelength_nm]
    sample = [float(v) for v in sample_on]
    if not wl:
        raise ValueError("empty spectrum")

    blank_match: Optional[bool] = None
    blank_notes: list[str] = []
    if sample_settings is not None and blank_settings is not None:
        blank_match, blank_notes = blank_settings_compatible(
            sample_settings, blank_settings
        )

    if blank_path is not None and (blank_wl is None or blank_i is None):
        blank_wl, blank_i = load_blank_intensity_csv(Path(blank_path))

    corrected = list(sample)
    blank_vals = [0.0] * len(sample)
    transmittance: list[float] = []
    absorbance: list[float] = []

    if blank_wl is not None and blank_i is not None:
        if mode == "transmission":
            ta = compute_transmission_absorbance(wl, sample, blank_wl, blank_i)
            wl = ta.wavelength_nm
            sample = ta.sample_on
            blank_vals = ta.reference
            corrected = ta.transmittance
            transmittance = ta.transmittance
            absorbance = ta.absorbance
        else:
            sub: BlankSubtractedSpectrum = subtract_blank(wl, sample, blank_wl, blank_i)
            wl = sub.wavelength_nm
            sample = sub.sample_on
            blank_vals = sub.blank
            corrected = sub.corrected

    clipped = any(abs(v) >= CLIP_THRESHOLD for v in sample)

    peak_nm: Optional[float] = None
    peak_i: Optional[float] = None
    delta: Optional[float] = None
    absolute_snr: Optional[float] = None
    found = find_local_max_near(
        wl, corrected, float(guide_nm), half_window_nm=float(half_window_nm)
    )
    if found is not None:
        peak_nm, peak_i = found
        delta = peak_nm - float(guide_nm)

    try:
        snr: RamanSnrResult = compute_raman_snr(
            wl,
            corrected,
            guide_nm=float(guide_nm),
            half_window_nm=float(half_window_nm),
            noise_lo_nm=float(noise_lo_nm),
            noise_hi_nm=float(noise_hi_nm),
        )
        absolute_snr = snr.snr
        if peak_nm is None:
            peak_nm = snr.peak_nm
            peak_i = snr.peak_intensity
            delta = peak_nm - float(guide_nm)
    except ValueError:
        pass

    continuum_fit: list[float] = []
    residual: list[float] = []
    residual_peak_nm: Optional[float] = None
    residual_peak_delta_i: Optional[float] = None
    contrast_snr: Optional[float] = None
    try:
        wing = compute_wing_continuum_residual(
            wl,
            corrected,
            left_wing=left_wing,
            right_wing=right_wing,
            peak_search=(float(guide_nm), float(half_window_nm)),
        )
        continuum_fit = wing.continuum_fit
        residual = wing.residual
        residual_peak_nm = wing.residual_peak_nm
        residual_peak_delta_i = wing.residual_peak_delta_i
        if residual_peak_delta_i is not None:
            contrast_snr = compute_contrast_snr(
                residual,
                wl,
                residual_peak_delta_i=residual_peak_delta_i,
                noise_lo_nm=float(noise_lo_nm),
                noise_hi_nm=float(noise_hi_nm),
                guide_nm=float(guide_nm),
                half_window_nm=float(half_window_nm),
            )
    except ValueError:
        pass

    return RunReviewResult(
        wavelength_nm=wl,
        sample_on=sample,
        blank=blank_vals,
        corrected=corrected,
        continuum_fit=continuum_fit,
        residual=residual,
        peak_nm=peak_nm,
        peak_intensity=peak_i,
        delta_nm=delta,
        absolute_snr=absolute_snr,
        contrast_snr=contrast_snr,
        residual_peak_nm=residual_peak_nm,
        residual_peak_delta_i=residual_peak_delta_i,
        clipped=clipped,
        blank_settings_match=blank_match,
        blank_match_notes=blank_notes,
        transmittance=transmittance,
        absorbance=absorbance,
        mode=mode,
    )


def discover_logged_runs(
    logs_root: Path,
    *,
    glob_patterns: Sequence[str] = (
        "freepath/*.json",
        "water-raman/*.json",
        "tonic-water/*.json",
        "scans/*.json",
        "dashboard/scans/*.json",
    ),
) -> list[dict[str, Any]]:
    """Index run sidecars under ``logs/`` (skips *-summary.json)."""
    root = Path(logs_root)
    runs: list[dict[str, Any]] = []
    if not root.is_dir():
        return runs
    seen: set[Path] = set()
    for pattern in glob_patterns:
        for path in sorted(root.glob(pattern)):
            if path in seen or path.name.endswith("-summary.json"):
                continue
            seen.add(path)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            runs.append(
                {
                    "run_id": path.stem,
                    "path": str(path),
                    "experiment": data.get("experiment"),
                    "series_id": data.get("series_id"),
                    "replicate_kind": data.get("replicate_kind"),
                    "passed": data.get("passed"),
                    "dilution": data.get("dilution"),
                    "settings": data.get("settings") or data.get("ls55_optics") or {},
                    "csv": (data.get("csv") or (data.get("artifacts") or {}).get("csv")),
                    "png": (data.get("png") or (data.get("artifacts") or {}).get("png")),
                    "peak": data.get("peak")
                    or (data.get("review_analysis") or {}).get("peak"),
                    "clipped": data.get("clipped")
                    or (data.get("review_analysis") or {}).get("clipped"),
                }
            )
    return runs


def discover_blank_candidates(
    logs_root: Path,
    *,
    glob_patterns: Sequence[str] = (
        "freepath/*.csv",
        "water-raman/*.csv",
        "tonic-water/*.csv",
        "scans/*.csv",
        "dashboard/scans/*.csv",
    ),
) -> list[dict[str, Any]]:
    """List CSV files that can serve as blank / I0 references."""
    root = Path(logs_root)
    out: list[dict[str, Any]] = []
    if not root.is_dir():
        return out
    for pattern in glob_patterns:
        for path in sorted(root.glob(pattern)):
            # Prefer freepath / corrected shapes; skip if unreadable later.
            meta: dict[str, Any] = {"path": str(path), "name": path.name}
            sidecar = path.with_suffix(".json")
            if sidecar.is_file():
                try:
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                    settings = data.get("settings") or data.get("ls55_optics") or {}
                    meta["settings"] = settings
                    meta["experiment"] = data.get("experiment")
                except (OSError, json.JSONDecodeError):
                    pass
            out.append(meta)
    return out


def load_spectrum_csv(path: Path) -> tuple[list[float], list[float]]:
    """
    Load wavelength + primary intensity from freepath or corrected CSV.

    Prefer ``corrected``, then ``sample_on``, then ``empty_on``.
    """
    import csv

    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "wavelength_nm" not in reader.fieldnames:
            raise ValueError(f"{path}: expected wavelength_nm column")
        fields = set(reader.fieldnames)
        if "corrected" in fields:
            key = "corrected"
        elif "sample_on" in fields:
            key = "sample_on"
        elif "empty_on" in fields:
            key = "empty_on"
        else:
            raise ValueError(
                f"{path}: expected corrected, sample_on, or empty_on; got {reader.fieldnames}"
            )
        wl: list[float] = []
        inten: list[float] = []
        for row in reader:
            wl.append(float(row["wavelength_nm"]))
            inten.append(float(row[key]))
    if not wl:
        raise ValueError(f"{path}: no data rows")
    return wl, inten
