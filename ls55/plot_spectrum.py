"""Matplotlib helpers for LS 55 spectrum plots."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence


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
