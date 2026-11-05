#!/usr/bin/env python3
"""Tonic-water quinine emission scan with matched solvent blank subtraction."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.freepath import run_freepath
from ls55.plot_spectrum import (
    annotate_guide_peaks,
    load_blank_intensity_csv,
    plot_annotated_emission,
    subtract_blank,
    write_corrected_csv,
)
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport

GUIDE_NM = 450.0
DEFAULT_HALF_WINDOW_NM = 25.0
CLIP_THRESHOLD = 900000.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LS 55 tonic-water usefulness gate: dark + sample ON, subtract a "
            "matched solvent (water-in-cuvette) blank, annotate the ~450 nm "
            "quinine emission band. Always ends source OFF."
        )
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="Serial device path")
    src.add_argument("--fixture-dir", type=Path, help="Offline fixture directory")
    parser.add_argument(
        "--stage2-pass",
        action="store_true",
        help="Operator sign-off that Stage 2 / Gate C passed",
    )
    parser.add_argument(
        "--sample-loaded",
        action="store_true",
        help="Quartz cuvette with tonic dilution seated; door fully closed",
    )
    parser.add_argument(
        "--blank",
        type=Path,
        required=True,
        help=(
            "Matched solvent-blank CSV (same Ex/slits/speed/step): freepath "
            "empty_on or corrected sample_on intensity column"
        ),
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "tonic-water",
    )
    parser.add_argument(
        "--dilution",
        default="1:80",
        help="Tonic:total dilution tag (default 1:80)",
    )
    parser.add_argument(
        "--replicate-kind",
        choices=("sanity", "technical", "reseat"),
        default=None,
        help="Tag this acquisition for series aggregation",
    )
    parser.add_argument(
        "--series-id",
        default=None,
        help="Series identifier shared across usefulness-gate replicates",
    )
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--motion-timeout", type=float, default=60.0)
    parser.add_argument("--scan-timeout", type=float, default=180.0)
    parser.add_argument("--ex", type=float, default=350.0)
    parser.add_argument("--em-lo", type=float, default=400.0)
    parser.add_argument("--em-hi", type=float, default=550.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--speed", type=int, default=120)
    parser.add_argument("--slit", type=float, default=5.0)
    parser.add_argument(
        "--guide",
        type=float,
        default=GUIDE_NM,
        help="Guide peak wavelength in nm (default 450)",
    )
    parser.add_argument(
        "--half-window",
        type=float,
        default=DEFAULT_HALF_WINDOW_NM,
        help="Local-max half-window around guide (default 25)",
    )
    args = parser.parse_args(argv)

    if not args.stage2_pass:
        print(
            "Refusing: pass --stage2-pass after Stage 2 PASS.",
            file=sys.stderr,
        )
        return 2
    if not args.sample_loaded:
        print(
            "Refusing: pass --sample-loaded (quartz + tonic dilution, door shut).",
            file=sys.stderr,
        )
        return 2
    if not args.blank.is_file():
        print(f"Refusing: blank CSV not found: {args.blank}", file=sys.stderr)
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"tonic-water-{stamp}.log"
    summary_path = args.log_dir / f"tonic-water-{stamp}.json"
    csv_path = args.log_dir / f"tonic-water-{stamp}.csv"
    png_path = args.log_dir / f"tonic-water-{stamp}.png"

    if args.fixture_dir is not None:
        inner = FakeTransport.from_fixture_dir(args.fixture_dir)
    else:
        inner = SerialTransport(args.port, baudrate=args.baud, timeout=0.05)

    transport = LoggingTransport(inner, raw_log)
    try:
        engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)
        result = run_freepath(
            engine,
            stage2_pass=True,
            compartment_closed=True,
            ex_nm=args.ex,
            em_lo=args.em_lo,
            em_hi=args.em_hi,
            interval_nm=args.interval,
            speed=args.speed,
            slit_nm=args.slit,
            motion_timeout_s=args.motion_timeout,
            scan_timeout_s=args.scan_timeout,
        )
    finally:
        transport.close()

    clipped = False
    max_abs = None
    if result.empty_on is not None:
        max_abs = result.empty_on.max_abs_intensity
        clipped = bool(max_abs is not None and max_abs >= CLIP_THRESHOLD)
        if any("0107" in (w or "") for w in result.warnings):
            clipped = True

    summary = result.to_dict()
    summary["experiment"] = "tonic-water"
    summary["sample"] = f"tonic water {args.dilution}"
    summary["dilution"] = args.dilution
    summary["expected"] = {
        "feature": "quinine emission",
        "guide_nm": args.guide,
        "ex_nm": args.ex,
        "half_window_nm": args.half_window,
    }
    summary["baud"] = args.baud
    summary["blank_csv"] = str(args.blank)
    summary["replicate_kind"] = args.replicate_kind
    summary["series_id"] = args.series_id
    summary["clipped"] = clipped
    summary["max_abs_intensity"] = max_abs
    summary["raw_log"] = str(raw_log)
    summary["csv"] = None
    summary["png"] = None
    summary["peaks"] = []
    summary["peak"] = None
    summary["postprocess_errors"] = []

    if (
        result.passed
        and result.empty_on is not None
        and result.empty_on.intensity
    ):
        try:
            blank_wl, blank_i = load_blank_intensity_csv(args.blank)
            spectrum = subtract_blank(
                result.empty_on.wavelength_nm,
                result.empty_on.intensity,
                blank_wl,
                blank_i,
            )
            peaks = annotate_guide_peaks(
                spectrum.wavelength_nm,
                spectrum.corrected,
                guide_nm=(args.guide,),
                guide_labels=(f"Quinine ~{args.guide:g}",),
                half_window_nm=args.half_window,
            )
            guide_peak = next(
                (p for p in peaks if p.guide_nm is not None),
                None,
            )
            write_corrected_csv(
                csv_path,
                wavelength_nm=spectrum.wavelength_nm,
                sample_on=spectrum.sample_on,
                blank=spectrum.blank,
                corrected=spectrum.corrected,
            )
            peak_note = ""
            if guide_peak is not None:
                delta = guide_peak.observed_nm - args.guide
                peak_note = (
                    f"  peak={guide_peak.observed_nm:g} nm"
                    f"  Δ={delta:+.1f} nm"
                    f"  I={guide_peak.observed_intensity:.0f}"
                )
            plot_annotated_emission(
                png_path,
                wavelength_nm=spectrum.wavelength_nm,
                corrected=spectrum.corrected,
                peaks=peaks,
                title=f"Tonic water {args.dilution} (blank-subtracted)",
                subtitle=(
                    f"ex={args.ex:g} nm  slits={args.slit:g} nm  "
                    f"Em {args.em_lo:g}–{args.em_hi:g} nm  SI={args.interval:g}"
                    f"{peak_note}"
                    + ("  CLIPPED" if clipped else "")
                ),
                blank_path=args.blank,
            )
            summary["csv"] = str(csv_path)
            summary["png"] = str(png_path)
            summary["peaks"] = [asdict(p) for p in peaks]
            if guide_peak is not None:
                summary["peak"] = {
                    "observed_nm": guide_peak.observed_nm,
                    "observed_intensity": guide_peak.observed_intensity,
                    "delta_nm": guide_peak.observed_nm - args.guide,
                    "guide_nm": args.guide,
                }
            if clipped:
                result.warnings.append(
                    f"intensity near clip ceiling "
                    f"(max |I|={max_abs}); dilute further before series"
                )
                summary["warnings"] = result.warnings
        except (OSError, ValueError) as exc:
            summary["postprocess_errors"].append(str(exc))
            result.errors.append(f"postprocess: {exc}")
            result.passed = False
            summary["passed"] = False
            if "errors" in summary:
                summary["errors"] = result.errors

    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"raw_log={raw_log}", file=sys.stderr)
    print(f"summary={summary_path}", file=sys.stderr)
    if summary["csv"]:
        print(f"csv={csv_path}", file=sys.stderr)
    if summary["png"]:
        print(f"png={png_path}", file=sys.stderr)

    if result.passed and not summary["postprocess_errors"]:
        print(
            "PASS" + (" with warnings" if result.warnings else ""),
            file=sys.stderr,
        )
        return 0
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
