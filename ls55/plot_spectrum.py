"""Matplotlib helpers for LS 55 spectrum plots."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple


def plot_freepath_comparison(
    path: Path,
    *,
    wavelength_nm: Sequence[float],
    dark: Sequence[float],
    empty_on: Sequence[float],
    title: str = "LS55 free-path empty compartment",
    subtitle: Optional[str] = None,
) -> Path:
    """Write a dark vs empty-ON intensity plot to ``path`` (PNG)."""
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8.0, 4.5), layout="constrained")
    ax.plot(wavelength_nm, dark, label="dark (ES=1)", color="#334155", linewidth=1.5)
    ax.plot(
        wavelength_nm,
        empty_on,
        label="empty ON (ES=0)",
        color="#b45309",
        linewidth=1.5,
    )
    ax.set_xlabel("Emission wavelength (nm)")
    ax.set_ylabel("Intensity (instrument counts)")
    full_title = title if not subtitle else f"{title}\n{subtitle}"
    ax.set_title(full_title)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def write_freepath_csv(
    path: Path,
    *,
    wavelength_nm: Sequence[float],
    dark: Sequence[float],
    empty_on: Sequence[float],
) -> Path:
    """Write ``wavelength_nm,dark,empty_on`` CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = min(len(wavelength_nm), len(dark), len(empty_on))
    lines = ["wavelength_nm,dark,empty_on\n"]
    for i in range(n):
        lines.append(f"{wavelength_nm[i]},{dark[i]},{empty_on[i]}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def load_freepath_csv(
    path: Path,
) -> Tuple[list[float], list[float], list[float]]:
    """Load ``wavelength_nm,dark,empty_on`` columns from a freepath CSV."""
    path = Path(path)
    wavelength_nm: list[float] = []
    dark: list[float] = []
    empty_on: list[float] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"wavelength_nm", "dark", "empty_on"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{path}: expected columns wavelength_nm,dark,empty_on; "
                f"got {reader.fieldnames!r}"
            )
        for row in reader:
            wavelength_nm.append(float(row["wavelength_nm"]))
            dark.append(float(row["dark"]))
            empty_on.append(float(row["empty_on"]))
    if not wavelength_nm:
        raise ValueError(f"{path}: no data rows")
    return wavelength_nm, dark, empty_on


def load_blank_intensity_csv(
    path: Path,
) -> Tuple[list[float], list[float]]:
    """
    Load blank wavelength + ON intensity from freepath or corrected CSV.

    Accepts either:
    - freepath shape: ``wavelength_nm,dark,empty_on`` (uses ``empty_on``)
    - corrected shape: ``wavelength_nm,sample_on,...`` (uses ``sample_on``)

    Prefer freepath column shape for solvent blanks acquired with the freepath
    runner (water-in-cuvette ON spectrum stored as ``empty_on``).
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: missing CSV header")
        fields = set(reader.fieldnames)
        if "wavelength_nm" not in fields:
            raise ValueError(
                f"{path}: expected wavelength_nm column; got {reader.fieldnames!r}"
            )
        if "empty_on" in fields:
            intensity_key = "empty_on"
        elif "sample_on" in fields:
            intensity_key = "sample_on"
        else:
            raise ValueError(
                f"{path}: expected empty_on or sample_on intensity column; "
                f"got {reader.fieldnames!r}"
            )
        wavelength_nm: list[float] = []
        intensity: list[float] = []
        for row in reader:
            wavelength_nm.append(float(row["wavelength_nm"]))
            intensity.append(float(row[intensity_key]))
    if not wavelength_nm:
        raise ValueError(f"{path}: no data rows")
    return wavelength_nm, intensity


@dataclass(frozen=True)
class BlankSubtractedSpectrum:
    wavelength_nm: list[float]
    sample_on: list[float]
    blank: list[float]
    corrected: list[float]


def subtract_blank(
    sample_wl: Sequence[float],
    sample_i: Sequence[float],
    blank_wl: Sequence[float],
    blank_i: Sequence[float],
) -> BlankSubtractedSpectrum:
    """
    Align sample and blank on a shared rounded-nm grid and subtract.

    Returns ``corrected = sample_on - blank`` on the intersection.
    Raises ``ValueError`` if there is no overlapping wavelength.
    """
    blank_map = {round(float(w), 1): float(v) for w, v in zip(blank_wl, blank_i)}
    wavelength_nm: list[float] = []
    sample_on: list[float] = []
    blank: list[float] = []
    corrected: list[float] = []
    for w, v in zip(sample_wl, sample_i):
        key = round(float(w), 1)
        if key not in blank_map:
            continue
        b = blank_map[key]
        s = float(v)
        wavelength_nm.append(key)
        sample_on.append(s)
        blank.append(b)
        corrected.append(s - b)
    if not wavelength_nm:
        raise ValueError("no overlapping wavelengths between sample and blank")
    return BlankSubtractedSpectrum(
        wavelength_nm=wavelength_nm,
        sample_on=sample_on,
        blank=blank,
        corrected=corrected,
    )


def write_corrected_csv(
    path: Path,
    *,
    wavelength_nm: Sequence[float],
    sample_on: Sequence[float],
    blank: Sequence[float],
    corrected: Sequence[float],
) -> Path:
    """Write ``wavelength_nm,sample_on,blank,corrected`` CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = min(len(wavelength_nm), len(sample_on), len(blank), len(corrected))
    lines = ["wavelength_nm,sample_on,blank,corrected\n"]
    for i in range(n):
        lines.append(
            f"{wavelength_nm[i]},{sample_on[i]},{blank[i]},{corrected[i]}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")
    return path


@dataclass(frozen=True)
class PeakAnnotation:
    label: str
    guide_nm: Optional[float]
    observed_nm: float
    observed_intensity: float


def find_local_max_near(
    wavelength_nm: Sequence[float],
    intensity: Sequence[float],
    center_nm: float,
    *,
    half_window_nm: float = 8.0,
) -> Optional[Tuple[float, float]]:
    """Return ``(wl, intensity)`` of the max within ``center ± half_window``."""
    best: Optional[Tuple[float, float]] = None
    for w, v in zip(wavelength_nm, intensity):
        if abs(float(w) - center_nm) > half_window_nm:
            continue
        if best is None or float(v) > best[1]:
            best = (float(w), float(v))
    return best


def annotate_guide_peaks(
    wavelength_nm: Sequence[float],
    intensity: Sequence[float],
    *,
    guide_nm: Sequence[float] = (),
    guide_labels: Optional[Sequence[str]] = None,
    half_window_nm: float = 8.0,
) -> list[PeakAnnotation]:
    """Build guide-wavelength + observed-local-max peak annotations."""
    if not wavelength_nm or not intensity:
        return []
    labels = list(guide_labels) if guide_labels is not None else []
    while len(labels) < len(guide_nm):
        labels.append(f"Guide {guide_nm[len(labels)]:g}")
    peaks: list[PeakAnnotation] = []
    for guide, label in zip(guide_nm, labels):
        found = find_local_max_near(
            wavelength_nm,
            intensity,
            float(guide),
            half_window_nm=half_window_nm,
        )
        if found is None:
            continue
        peaks.append(
            PeakAnnotation(
                label=label,
                guide_nm=float(guide),
                observed_nm=found[0],
                observed_intensity=found[1],
            )
        )
    # Global maximum in-window — skip if a guide peak already marks it.
    global_i = max(range(len(intensity)), key=lambda i: float(intensity[i]))
    global_nm = float(wavelength_nm[global_i])
    if not any(abs(p.observed_nm - global_nm) <= 2.0 for p in peaks):
        peaks.append(
            PeakAnnotation(
                label="Observed max",
                guide_nm=None,
                observed_nm=global_nm,
                observed_intensity=float(intensity[global_i]),
            )
        )
    elif peaks:
        # Prefer naming the matching guide peak as the observed max.
        match = min(peaks, key=lambda p: abs(p.observed_nm - global_nm))
        if abs(match.observed_nm - global_nm) <= 2.0 and "max" not in match.label.lower():
            peaks = [
                PeakAnnotation(
                    label=f"{match.label} (max)",
                    guide_nm=match.guide_nm,
                    observed_nm=match.observed_nm,
                    observed_intensity=match.observed_intensity,
                )
                if p is match
                else p
                for p in peaks
            ]
    return peaks


@dataclass(frozen=True)
class RamanSnrResult:
    peak_nm: float
    peak_intensity: float
    noise_rms: float
    snr: Optional[float]
    noise_lo_nm: float
    noise_hi_nm: float
    n_noise_points: int


def compute_raman_snr(
    wavelength_nm: Sequence[float],
    intensity: Sequence[float],
    *,
    guide_nm: float = 397.0,
    half_window_nm: float = 8.0,
    noise_lo_nm: float = 410.0,
    noise_hi_nm: float = 420.0,
) -> RamanSnrResult:
    """
    Peak / RMS-noise SNR on a blank-corrected spectrum.

    Peak is the local max near ``guide_nm``. Noise points are intensities in
    ``[noise_lo_nm, noise_hi_nm]`` excluding the peak half-window. SNR is
    ``peak_intensity / noise_rms`` when RMS > 0; otherwise ``snr`` is None.
    """
    if not wavelength_nm or not intensity:
        raise ValueError("wavelength_nm and intensity must be non-empty")
    if noise_hi_nm < noise_lo_nm:
        raise ValueError("noise_hi_nm must be >= noise_lo_nm")

    found = find_local_max_near(
        wavelength_nm,
        intensity,
        float(guide_nm),
        half_window_nm=half_window_nm,
    )
    if found is None:
        raise ValueError(
            f"no intensity samples within {guide_nm:g} ± {half_window_nm:g} nm"
        )
    peak_nm, peak_intensity = found

    noise_vals: list[float] = []
    for w, v in zip(wavelength_nm, intensity):
        wl = float(w)
        if wl < float(noise_lo_nm) or wl > float(noise_hi_nm):
            continue
        if abs(wl - float(guide_nm)) <= float(half_window_nm):
            continue
        noise_vals.append(float(v))
    if not noise_vals:
        raise ValueError(
            f"no noise samples in [{noise_lo_nm:g}, {noise_hi_nm:g}] nm "
            f"outside guide ± {half_window_nm:g} nm"
        )

    mean = sum(noise_vals) / len(noise_vals)
    variance = sum((x - mean) ** 2 for x in noise_vals) / len(noise_vals)
    noise_rms = variance ** 0.5
    snr = (peak_intensity / noise_rms) if noise_rms > 0.0 else None
    return RamanSnrResult(
        peak_nm=peak_nm,
        peak_intensity=peak_intensity,
        noise_rms=noise_rms,
        snr=snr,
        noise_lo_nm=float(noise_lo_nm),
        noise_hi_nm=float(noise_hi_nm),
        n_noise_points=len(noise_vals),
    )


def plot_annotated_emission(
    path: Path,
    *,
    wavelength_nm: Sequence[float],
    corrected: Sequence[float],
    peaks: Sequence[PeakAnnotation],
    title: str = "Emission spectrum (blank-subtracted)",
    subtitle: Optional[str] = None,
    blank_path: Optional[Path] = None,
) -> Path:
    """Plot corrected emission with literature guides and observed peaks."""
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9.0, 5.2), layout="constrained")
    ax.plot(
        wavelength_nm,
        corrected,
        label="corrected (sample − blank)",
        color="#166534",
        linewidth=1.6,
    )

    if corrected:
        data_min = min(float(v) for v in corrected)
        data_max = max(float(v) for v in corrected)
        pad = max(1.0, 0.08 * (data_max - data_min or 1.0))
        ax.set_ylim(data_min - pad, data_max + pad * 1.35)

    guide_drawn: set[float] = set()
    ordered = sorted(peaks, key=lambda p: p.observed_nm)
    for peak in ordered:
        if peak.guide_nm is not None and peak.guide_nm not in guide_drawn:
            ax.axvline(
                peak.guide_nm,
                color="#94a3b8",
                linestyle="--",
                linewidth=1.0,
                alpha=0.85,
                label="literature guide" if not guide_drawn else None,
            )
            guide_drawn.add(peak.guide_nm)
        ax.plot(
            peak.observed_nm,
            peak.observed_intensity,
            marker="o",
            markersize=6,
            color="#b45309",
            zorder=5,
        )

    # Peak names live in a callout box — avoids stacking when observed
    # maxima sit only a few nm apart (e.g. 526 vs 530).
    if ordered:
        lines = ["Peaks"]
        for peak in ordered:
            guide = (
                f"  (guide {peak.guide_nm:g})"
                if peak.guide_nm is not None
                else ""
            )
            lines.append(
                f"{peak.label}: {peak.observed_nm:g} nm"
                f"  I={peak.observed_intensity:.0f}{guide}"
            )
        ax.text(
            0.98,
            0.97,
            "\n".join(lines),
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8,
            color="#334155",
            family="monospace",
            linespacing=1.55,
            bbox={
                "boxstyle": "round,pad=0.55",
                "facecolor": "white",
                "edgecolor": "#cbd5e1",
                "alpha": 0.92,
            },
            zorder=6,
        )

    ax.set_xlabel("Emission wavelength (nm)")
    ax.set_ylabel("Intensity (instrument counts)")
    parts = [title]
    if subtitle:
        parts.append(subtitle)
    if blank_path is not None:
        parts.append(f"blank={Path(blank_path).name}")
    ax.set_title("\n".join(parts))
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_sample_vs_freepath_comparison(
    path: Path,
    *,
    wavelength_nm: Sequence[float],
    sample_on: Sequence[float],
    blank: Sequence[float],
    corrected: Sequence[float],
    title: str = "Sample vs freepath blank (shared scale)",
    subtitle: Optional[str] = None,
    blank_path: Optional[Path] = None,
    sample_panel_title: str = "Sample",
) -> Path:
    """
    Two-panel comparison: sample/corrected vs freepath blank on identical axes.

    Shares Em wavelength limits and intensity limits so the blank floor is
    visually comparable to the sample band.
    """
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wl = [float(w) for w in wavelength_nm]
    sample = [float(v) for v in sample_on]
    blank_i = [float(v) for v in blank]
    corr = [float(v) for v in corrected]
    if not wl:
        raise ValueError("wavelength_nm is empty")

    y_vals = sample + blank_i + corr
    y_min = min(y_vals)
    y_max = max(y_vals)
    pad = max(1.0, 0.08 * (y_max - y_min or 1.0))
    ylim = (max(0.0, y_min - pad), y_max + pad)
    xlim = (min(wl), max(wl))

    fig, (ax_sample, ax_blank) = plt.subplots(
        2,
        1,
        figsize=(9.0, 7.0),
        sharex=True,
        sharey=True,
        layout="constrained",
    )

    ax_sample.plot(
        wl, sample, color="#166534", linewidth=1.5, label="sample ON"
    )
    ax_sample.plot(
        wl, corr, color="#15803d", linewidth=1.5, linestyle="--", label="corrected"
    )
    ax_sample.set_ylabel("Intensity (instrument counts)")
    ax_sample.legend(loc="upper left")
    ax_sample.grid(True, alpha=0.3)
    ax_sample.set_title(sample_panel_title)

    ax_blank.plot(
        wl,
        blank_i,
        color="#b45309",
        linewidth=1.5,
        label="freepath empty_on",
    )
    ax_blank.set_xlabel("Emission wavelength (nm)")
    ax_blank.set_ylabel("Intensity (instrument counts)")
    ax_blank.legend(loc="upper left")
    ax_blank.grid(True, alpha=0.3)
    blank_name = Path(blank_path).name if blank_path is not None else "blank"
    ax_blank.set_title(f"Freepath blank ({blank_name})")

    for ax in (ax_sample, ax_blank):
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)

    parts = [title]
    if subtitle:
        parts.append(subtitle)
    fig.suptitle("\n".join(parts))
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
