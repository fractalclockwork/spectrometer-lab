#!/usr/bin/env python3
"""Run LS 55 Stage-1 serial system check (live port or offline fixtures)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running from repo root without installation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.stage1 import run_stage1
from ls55.transactions import TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LS 55 Stage-1 power-on / serial system check"
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--port",
        help="Serial device path (prefer /dev/serial/by-id/...)",
    )
    src.add_argument(
        "--fixture-dir",
        type=Path,
        help="Offline fixture directory containing script.json",
    )
    parser.add_argument(
        "--gate-a-pass",
        action="store_true",
        help="Operator sign-off that Gate A safety checks passed",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "stage1",
        help="Directory for raw TX/RX logs and JSON summary",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=9600,
        help="Baud rate (default 9600 per manual; override only if scope bit-time differs)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Transaction timeout in seconds",
    )
    parser.add_argument(
        "--skip-optional-readbacks",
        action="store_true",
        help="Skip parameterless $GM/$SX/$SM/$FW/$PH queries",
    )
    args = parser.parse_args(argv)

    if not args.gate_a_pass:
        print(
            "Refusing to run: pass --gate-a-pass after Gate A checklist is PASS.",
            file=sys.stderr,
        )
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"stage1-{stamp}.log"
    summary_path = args.log_dir / f"stage1-{stamp}.json"

    if args.fixture_dir is not None:
        inner = FakeTransport.from_fixture_dir(args.fixture_dir)
    else:
        # Short pyserial poll; TransactionEngine owns overall deadlines.
        inner = SerialTransport(args.port, baudrate=args.baud, timeout=0.05)

    transport = LoggingTransport(inner, raw_log)
    try:
        engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)
        result = run_stage1(
            engine,
            gate_a_pass=True,
            include_optional_readbacks=not args.skip_optional_readbacks,
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
        if result.warnings:
            print("PASS with warnings", file=sys.stderr)
        else:
            print("PASS", file=sys.stderr)
        return 0
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
