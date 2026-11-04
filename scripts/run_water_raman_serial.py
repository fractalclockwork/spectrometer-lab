#!/usr/bin/env python3
"""Distilled-water Raman scan with freepath blank subtraction, peak labels, SNR."""

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
    compute_raman_snr,
    load_freepath_csv,
    plot_annotated_emission,
    subtract_blank,
    write_corrected_csv,
)
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport

GUIDE_NM = 397.0
DEFAULT_NOISE_LO = 410.0
DEFAULT_NOISE_HI = 420.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LS 55 distilled-water Raman: dark + sample ON, subtract a matched "
            "freepath empty_on blank, annotate the ~397 nm O–H Raman band, and "
            "report RMS SNR. Always ends source OFF."
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
        help="Quartz cuvette with distilled water seated; door fully closed",
    )
    parser.add_argument(
        "--blank",
        type=Path,
        required=True,
        help="Matched freepath CSV blank (same Ex/slits/speed/step as this run)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "water-raman",
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
        help="Series identifier shared across calibration replicates",
    )
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--motion-timeout", type=float, default=60.0)
    parser.add_argument("--scan-timeout", type=float, default=180.0)
    parser.add_argument("--ex", type=float, default=350.0)
    parser.add_argument("--em-lo", type=float, default=380.0)
    parser.add_argument("--em-hi", type=float, default=420.0)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--speed", type=int, default=120)
    parser.add_argument("--slit", type=float, default=10.0)
    parser.add_argument("--noise-lo", type=float, default=DEFAULT_NOISE_LO)
    parser.add_argument("--noise-hi", type=float, default=DEFAULT_NOISE_HI)
    args = parser.parse_args(argv)

    if not args.stage2_pass:
        print(
            "Refusing: pass --stage2-pass after Stage 2 PASS.",
            file=sys.stderr,
        )
        return 2
    if not args.sample_loaded:
        print(
            "Refusing: pass --sample-loaded (quartz + distilled water, door shut).",
            file=sys.stderr,
        )
        return 2
    if not args.blank.is_file():
        print(f"Refusing: blank CSV not found: {args.blank}", file=sys.stderr)
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"water-raman-{stamp}.log"
    summary_path = args.log_dir / f"water-raman-{stamp}.json"
    csv_path = args.log_dir / f"water-raman-{stamp}.csv"
    png_path = args.log_dir / f"water-raman-{stamp}.png"

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

    summary = result.to_dict()
    summary["experiment"] = "water-raman"
    summary["sample"] = "distilled water"
    summary["expected"] = {
        "feature": "water O-H Raman",
        "guide_nm": GUIDE_NM,
        "ex_nm": args.ex,
    }
    summary["baud"] = args.baud
    summary["blank_csv"] = str(args.blank)
    summary["replicate_kind"] = args.replicate_kind
    summary["series_id"] = args.series_id
    summary["raw_log"] = str(raw_log)
    summary["csv"] = None
    summary["png"] = None
    summary["peaks"] = []
    summary["snr"] = None
    summary["postprocess_errors"] = []

    if (
        result.passed
        and result.empty_on is not None
        and result.empty_on.intensity
    ):
        try:
            blank_wl, _, blank_empty = load_freepath_csv(args.blank)
            spectrum = subtract_blank(
                result.empty_on.wavelength_nm,
                result.empty_on.intensity,
                blank_wl,
                blank_empty,
            )
            peaks = annotate_guide_peaks(
                spectrum.wavelength_nm,
                spectrum.corrected,
                guide_nm=(GUIDE_NM,),
                guide_labels=("Water Raman ~397",),
            )
            snr = compute_raman_snr(
                spectrum.wavelength_nm,
                spectrum.corrected,
                guide_nm=GUIDE_NM,
                noise_lo_nm=args.noise_lo,
                noise_hi_nm=args.noise_hi,
            )
            write_corrected_csv(
                csv_path,
                wavelength_nm=spectrum.wavelength_nm,
                sample_on=spectrum.sample_on,
                blank=spectrum.blank,
                corrected=spectrum.corrected,
            )
            plot_annotated_emission(
                png_path,
                wavelength_nm=spectrum.wavelength_nm,
                corrected=spectrum.corrected,
                peaks=peaks,
                title="Distilled water Raman (blank-subtracted)",
                subtitle=(
                    f"ex={args.ex:g} nm  slits={args.slit:g} nm  "
                    f"Em {args.em_lo:g}–{args.em_hi:g} nm  SI={args.interval:g}"
                    + (
                        f"  SNR={snr.snr:.1f}"
                        if snr.snr is not None
                        else "  SNR=n/a"
                    )
                ),
                blank_path=args.blank,
            )
            summary["csv"] = str(csv_path)
            summary["png"] = str(png_path)
            summary["peaks"] = [asdict(p) for p in peaks]
            summary["snr"] = asdict(snr)
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
