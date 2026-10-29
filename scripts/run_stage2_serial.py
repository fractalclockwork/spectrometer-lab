#!/usr/bin/env python3
"""Run LS 55 Stage-2 / Gate C motion + single-point data check (source OFF)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.stage2 import run_stage2
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LS 55 Stage-2 / Gate C: bounded motion and $RD (source OFF)"
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="Serial device path")
    src.add_argument("--fixture-dir", type=Path, help="Offline fixture directory")
    parser.add_argument(
        "--stage1-pass",
        action="store_true",
        help="Operator sign-off that Stage 1 / Gate B passed",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "stage2",
    )
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Default transaction timeout (motion uses --motion-timeout)",
    )
    parser.add_argument(
        "--motion-timeout",
        type=float,
        default=60.0,
        help="Timeout for $GM/$SX/$SM moves (seconds)",
    )
    parser.add_argument("--gm-ex", type=float, default=350.0)
    parser.add_argument("--gm-em", type=float, default=450.0)
    parser.add_argument("--slit", type=float, default=5.0)
    parser.add_argument("--rd-time", type=float, default=1.0)
    args = parser.parse_args(argv)

    if not args.stage1_pass:
        print(
            "Refusing to run: pass --stage1-pass after Stage 1 PASS.",
            file=sys.stderr,
        )
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"stage2-{stamp}.log"
    summary_path = args.log_dir / f"stage2-{stamp}.json"

    if args.fixture_dir is not None:
        inner = FakeTransport.from_fixture_dir(args.fixture_dir)
    else:
        # Short pyserial poll; TransactionEngine owns overall deadlines.
        inner = SerialTransport(args.port, baudrate=args.baud, timeout=0.05)

    transport = LoggingTransport(inner, raw_log)
    try:
        engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)
        result = run_stage2(
            engine,
            stage1_pass=True,
            gm_ex=args.gm_ex,
            gm_em=args.gm_em,
            slit_nm=args.slit,
            rd_time_s=args.rd_time,
            motion_timeout_s=args.motion_timeout,
        )
    finally:
        transport.close()

    summary = result.to_dict()
    summary["baud"] = args.baud
    summary["raw_log"] = str(raw_log)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"raw_log={raw_log}", file=sys.stderr)
    print(f"summary={summary_path}", file=sys.stderr)

    if result.passed:
        print("PASS" + (" with warnings" if result.warnings else ""), file=sys.stderr)
        return 0
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
