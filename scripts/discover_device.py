#!/usr/bin/env python3
"""Discover the LS 55, check busy/boot state, and safe-off the Xe source on first power-on."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.discover import list_candidate_ports, run_discover
from ls55.protocol import find_status_payload
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport


def _probe_is_ls55(port: str, *, baud: int, timeout: float) -> bool:
    """Return True if ``$ST`` yields a ``55…`` status payload on this port."""
    inner = SerialTransport(port, baudrate=baud, timeout=0.05)
    try:
        engine = TransactionEngine(inner, timeout_s=timeout, prompted=True)
        st = engine.transact("$ST")
    except (TimeoutError, ProtocolError, OSError):
        return False
    finally:
        inner.close()
    return find_status_payload(st.data_records) is not None or st.initial_code == "0110"


def _resolve_port(
    *,
    port: str | None,
    baud: int,
    timeout: float,
) -> tuple[str | None, list[str], str | None]:
    """
    Resolve a live serial port.

    Returns (chosen_port, candidates, error_message).
    """
    if port:
        return port, [port], None

    candidates = list_candidate_ports()
    if not candidates:
        return None, [], "no serial devices found under /dev/serial/by-id or pyserial"

    matches: list[str] = []
    for candidate in candidates:
        try:
            if _probe_is_ls55(candidate, baud=baud, timeout=timeout):
                matches.append(candidate)
        except OSError:
            continue

    if not matches:
        return None, candidates, f"no LS 55 response among candidates: {candidates}"
    if len(matches) > 1:
        return (
            None,
            candidates,
            f"multiple LS 55 candidates responded; pass --port explicitly: {matches}",
        )
    return matches[0], candidates, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Discover the LS 55, detect busy/boot, and enforce Xe OFF ($ES 1) as "
            "the idle resting state (lamp life + quieter bench)."
        )
    )
    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument(
        "--port",
        help="Serial device path (prefer /dev/serial/by-id/...). "
        "If omitted, auto-probe by-id candidates.",
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
        default=REPO_ROOT / "logs" / "discover",
        help="Directory for raw TX/RX logs and JSON summary",
    )
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-transaction timeout in seconds",
    )
    parser.add_argument(
        "--boot-wait",
        type=float,
        default=90.0,
        help="Seconds to wait for $ST during power-on homing (default 90)",
    )
    parser.add_argument(
        "--boot-poll",
        type=float,
        default=2.0,
        help="Seconds between boot $ST retries (default 2)",
    )
    args = parser.parse_args(argv)

    if not args.gate_a_pass:
        print(
            "Refusing: pass --gate-a-pass after Gate A checklist is PASS.",
            file=sys.stderr,
        )
        return 2

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"discover-{stamp}.log"
    summary_path = args.log_dir / f"discover-{stamp}.json"

    candidates: list[str] = []
    chosen_port: str | None = None

    if args.fixture_dir is not None:
        inner = FakeTransport.from_fixture_dir(args.fixture_dir)
        chosen_port = f"fixture:{args.fixture_dir}"
    else:
        chosen_port, candidates, resolve_err = _resolve_port(
            port=args.port,
            baud=args.baud,
            timeout=min(args.timeout, 3.0),
        )
        if resolve_err or chosen_port is None:
            summary = {
                "ready": False,
                "state": "no_device",
                "gate_a_pass": True,
                "port": args.port,
                "candidates": candidates,
                "errors": [resolve_err or "no port resolved"],
            }
            summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(summary, indent=2))
            print(f"summary={summary_path}", file=sys.stderr)
            print("FAIL", file=sys.stderr)
            return 1
        inner = SerialTransport(chosen_port, baudrate=args.baud, timeout=0.05)

    transport = LoggingTransport(inner, raw_log)
    try:
        engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)
        result = run_discover(
            engine,
            gate_a_pass=True,
            port=chosen_port,
            boot_wait_s=args.boot_wait,
            boot_poll_s=args.boot_poll,
        )
    finally:
        transport.close()

    summary = result.to_dict()
    summary["baud"] = args.baud
    summary["candidates"] = candidates
    summary["raw_log"] = str(raw_log)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"raw_log={raw_log}", file=sys.stderr)
    print(f"summary={summary_path}", file=sys.stderr)

    if result.ready:
        if result.lamp_disabled:
            print("READY (Xe forced OFF; was ON at probe)", file=sys.stderr)
        else:
            print("READY (Xe OFF resting state verified)", file=sys.stderr)
        return 0
    if result.state == "busy":
        print("BUSY", file=sys.stderr)
        return 1
    if result.state == "booting":
        print("BOOTING", file=sys.stderr)
        return 1
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
