#!/usr/bin/env python3
"""Cycle LS 55 excitation shutter / source ($ES): OFF → ON → OFF."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.es_cycle import run_es_cycle
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LS 55 $ES cycle: read → ON ($ES 0) → dwell → OFF ($ES 1). "
            "Polarity: 0=ON, 1=OFF. Always attempts to end OFF."
        )
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="Serial device path")
    src.add_argument("--fixture-dir", type=Path, help="Offline fixture directory")
    parser.add_argument(
        "--compartment-closed",
        action="store_true",
        help="Operator confirms sample compartment empty, dry, and fully closed",
    )
    parser.add_argument(
        "--on-dwell",
        type=float,
        default=2.0,
        help="Seconds to leave source ON before commanding OFF (default 2)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "es_cycle",
    )
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    if not args.compartment_closed:
        print(
            "Refusing: pass --compartment-closed (door shut, empty, no beam viewing).",
            file=sys.stderr,
        )
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"es_cycle-{stamp}.log"
    summary_path = args.log_dir / f"es_cycle-{stamp}.json"

    if args.fixture_dir is not None:
        inner = FakeTransport.from_fixture_dir(args.fixture_dir)
    else:
        inner = SerialTransport(args.port, baudrate=args.baud, timeout=0.05)

    transport = LoggingTransport(inner, raw_log)
    try:
        engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)
        result = run_es_cycle(
            engine,
            compartment_closed=True,
            on_dwell_s=args.on_dwell,
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
        print("PASS", file=sys.stderr)
        return 0
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
