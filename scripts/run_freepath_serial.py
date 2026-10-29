#!/usr/bin/env python3
"""Run LS 55 Stage-3 free-path empty-compartment emission scan (dark + ON)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.freepath import run_freepath
from ls55.plot_spectrum import plot_freepath_comparison, write_freepath_csv
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport


def _align_series(dark_wl, dark_i, on_wl, on_i):
    """Align dark/ON on shared wavelength grid (intersection by rounded nm)."""
    on_map = {round(w, 1): v for w, v in zip(on_wl, on_i)}
    wl, d, o = [], [], []
    for w, v in zip(dark_wl, dark_i):
        key = round(w, 1)
        if key in on_map:
            wl.append(key)
            d.append(v)
            o.append(on_map[key])
    return wl, d, o


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LS 55 Stage-3 free-path: emission scan dark (ES=1) then empty ON "
            "(ES=0). Always ends source OFF."
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
        "--compartment-closed",
        action="store_true",
        help="Sample compartment empty, dry, and fully closed",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "freepath",
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
    args = parser.parse_args(argv)

    if not args.stage2_pass:
        print(
            "Refusing: pass --stage2-pass after Stage 2 PASS.",
            file=sys.stderr,
        )
        return 2
    if not args.compartment_closed:
        print(
            "Refusing: pass --compartment-closed (door shut, empty).",
            file=sys.stderr,
        )
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"freepath-{stamp}.log"
    summary_path = args.log_dir / f"freepath-{stamp}.json"
    csv_path = args.log_dir / f"freepath-{stamp}.csv"
    png_path = args.log_dir / f"freepath-{stamp}.png"

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
    summary["baud"] = args.baud
    summary["raw_log"] = str(raw_log)
    summary["csv"] = None
    summary["png"] = None

    if result.dark and result.empty_on and result.dark.intensity and result.empty_on.intensity:
        wl, dark, on = _align_series(
            result.dark.wavelength_nm,
            result.dark.intensity,
            result.empty_on.wavelength_nm,
            result.empty_on.intensity,
        )
        if wl:
            write_freepath_csv(csv_path, wavelength_nm=wl, dark=dark, empty_on=on)
            plot_freepath_comparison(
                png_path,
                wavelength_nm=wl,
                dark=dark,
                empty_on=on,
                subtitle=f"ex={args.ex:g} nm  slits slits={args.slit:g} nm  SI={args.interval:g}",
            )
            summary["csv"] = str(csv_path)
            summary["png"] = str(png_path)

    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"raw_log={raw_log}", file=sys.stderr)
    print(f"summary={summary_path}", file=sys.stderr)
    if summary["csv"]:
        print(f"csv={csv_path}", file=sys.stderr)
    if summary["png"]:
        print(f"png={png_path}", file=sys.stderr)

    if result.passed:
        print("PASS" + (" with warnings" if result.warnings else ""), file=sys.stderr)
        return 0
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
