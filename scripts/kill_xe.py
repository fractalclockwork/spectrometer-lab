#!/usr/bin/env python3
"""Force LS 55 Xe / excitation shutter OFF ($ES 1). Safe idle for lamp life."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.discover import list_candidate_ports
from ls55.protocol import find_status_payload
from ls55.source import ensure_source_off
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine
from ls55.transport import FakeTransport, LoggingTransport, SerialTransport


def _probe_is_ls55(port: str, *, baud: int, timeout: float) -> bool:
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
            "Force Xe / excitation shutter OFF ($ES 1) and verify readback. "
            "No Gate A flag required — turning the source off is always safe."
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
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "kill_xe",
        help="Directory for raw TX/RX logs and JSON summary",
    )
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-transaction timeout in seconds",
    )
    args = parser.parse_args(argv)

    args.log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_log = args.log_dir / f"kill_xe-{stamp}.log"
    summary_path = args.log_dir / f"kill_xe-{stamp}.json"

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
                "ok": False,
                "port": args.port,
                "candidates": candidates,
                "errors": [resolve_err or "no port resolved"],
            }
            summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(summary, indent=2))
            print(f"summary={summary_path}", file=sys.stderr)
            print("FAIL (no device)", file=sys.stderr)
            return 1
        inner = SerialTransport(chosen_port, baudrate=args.baud, timeout=0.05)

    transport = LoggingTransport(inner, raw_log)
    try:
        engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)
        result = ensure_source_off(engine)
    finally:
        transport.close()

    summary = result.to_dict()
    summary["port"] = chosen_port
    summary["baud"] = args.baud
    summary["candidates"] = candidates
    summary["raw_log"] = str(raw_log)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"raw_log={raw_log}", file=sys.stderr)
    print(f"summary={summary_path}", file=sys.stderr)

    if result.ok:
        if result.was_on:
            print(f"Xe OFF (was ON)  port={chosen_port}", file=sys.stderr)
        else:
            print(f"Xe already OFF  port={chosen_port}", file=sys.stderr)
        return 0
    if result.busy:
        print("BUSY (instrument refused $ES; close competing serial users)", file=sys.stderr)
        return 1
    print("FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
