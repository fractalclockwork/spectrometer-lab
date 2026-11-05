#!/usr/bin/env python3
"""Aggregate tonic-water sidecars for a usefulness-gate series."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDE_NM = 450.0


def _mean_std(values: list[float]) -> tuple[Optional[float], Optional[float]]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(var)


def _peak_from_summary(data: dict[str, Any]) -> Optional[dict[str, float]]:
    peak = data.get("peak")
    if isinstance(peak, dict) and peak.get("observed_nm") is not None:
        observed = float(peak["observed_nm"])
        return {
            "observed_nm": observed,
            "observed_intensity": float(peak.get("observed_intensity") or 0.0),
            "delta_nm": float(peak.get("delta_nm", observed - GUIDE_NM)),
        }
    for item in data.get("peaks") or []:
        guide = item.get("guide_nm")
        if guide is None:
            continue
        if abs(float(guide) - GUIDE_NM) <= 0.5:
            observed = float(item["observed_nm"])
            return {
                "observed_nm": observed,
                "observed_intensity": float(item["observed_intensity"]),
                "delta_nm": observed - GUIDE_NM,
            }
    return None


def _stats_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    peaks = [r["peak"]["observed_nm"] for r in rows if r.get("peak")]
    deltas = [r["peak"]["delta_nm"] for r in rows if r.get("peak")]
    intensities = [
        r["peak"]["observed_intensity"] for r in rows if r.get("peak")
    ]
    peak_mean, peak_std = _mean_std(peaks)
    delta_mean, delta_std = _mean_std(deltas)
    intensity_mean, intensity_std = _mean_std(intensities)
    return {
        "n": len(rows),
        "peak_nm_mean": peak_mean,
        "peak_nm_std": peak_std,
        "delta_nm_mean": delta_mean,
        "delta_nm_std": delta_std,
        "intensity_mean": intensity_mean,
        "intensity_std": intensity_std,
        "n_clipped": sum(1 for r in rows if r.get("clipped")),
        "n_passed": sum(1 for r in rows if r.get("passed")),
        "runs": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fold tonic-water-*.json sidecars for a --series-id into peak "
            "stats split by replicate_kind."
        )
    )
    parser.add_argument("--series-id", required=True)
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "tonic-water",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output summary JSON (default: <log-dir>/<series-id>-summary.json)",
    )
    args = parser.parse_args(argv)

    if not args.log_dir.is_dir():
        print(f"Refusing: log dir not found: {args.log_dir}", file=sys.stderr)
        return 2

    out_path = args.out or (args.log_dir / f"{args.series_id}-summary.json")
    matched: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for path in sorted(args.log_dir.glob("tonic-water-*.json")):
        if path.name.endswith("-summary.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append({"path": str(path), "reason": str(exc)})
            continue
        if data.get("experiment") != "tonic-water":
            skipped.append(
                {
                    "path": str(path),
                    "reason": f"experiment={data.get('experiment')!r}",
                }
            )
            continue
        if data.get("series_id") != args.series_id:
            continue
        settings = data.get("settings") or {}
        peak = _peak_from_summary(data)
        matched.append(
            {
                "path": str(path),
                "replicate_kind": data.get("replicate_kind"),
                "dilution": data.get("dilution"),
                "passed": bool(data.get("passed")),
                "clipped": bool(data.get("clipped")),
                "settings": {
                    "ex_nm": settings.get("ex_nm"),
                    "em_lo": settings.get("em_lo"),
                    "em_hi": settings.get("em_hi"),
                    "interval_nm": settings.get("interval_nm"),
                    "speed": settings.get("speed"),
                    "slit_nm": settings.get("slit_nm"),
                },
                "peak": peak,
            }
        )

    by_kind: dict[str, list[dict[str, Any]]] = {
        "sanity": [],
        "technical": [],
        "reseat": [],
        "other": [],
    }
    for row in matched:
        kind = row.get("replicate_kind")
        if kind in ("sanity", "technical", "reseat"):
            by_kind[kind].append(row)
        else:
            by_kind["other"].append(row)

    gate = [r for r in matched if r.get("replicate_kind") in ("technical", "reseat")]
    dilutions = sorted(
        {str(r.get("dilution")) for r in matched if r.get("dilution")}
    )
    summary = {
        "series_id": args.series_id,
        "guide_nm": GUIDE_NM,
        "log_dir": str(args.log_dir),
        "dilutions": dilutions,
        "n_matched": len(matched),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "by_replicate_kind": {k: _stats_block(v) for k, v in by_kind.items()},
        "gate_technical_plus_reseat": _stats_block(gate),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    def _fmt(block: dict[str, Any], label: str) -> None:
        print(
            f"{label}: n={block['n']}  "
            f"peak={block['peak_nm_mean']}±{block['peak_nm_std']} nm  "
            f"Δ={block['delta_nm_mean']}±{block['delta_nm_std']} nm  "
            f"I={block['intensity_mean']}±{block['intensity_std']}  "
            f"clipped={block['n_clipped']} passed={block['n_passed']}"
        )

    print(
        f"series_id={args.series_id} matched={len(matched)} "
        f"skipped={len(skipped)} dilutions={dilutions}"
    )
    for kind in ("sanity", "technical", "reseat", "other"):
        block = summary["by_replicate_kind"][kind]
        if block["n"]:
            _fmt(block, kind)
    _fmt(summary["gate_technical_plus_reseat"], "gate")
    print(f"wrote={out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
