#!/usr/bin/env python3
"""Automated LS 55 serial comms probe with canonical hex dumps (Stage-1 commands)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ls55.hexdump import hexdump
from ls55.protocol import (
    encode_command,
    find_status_payload,
    me_status_code,
    parse_es_position,
    parse_status_payload,
)
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine
from ls55.transport import LoggingTransport, SerialTransport

# Comms-only validation sequence (no motion parameters, no calibration).
HARD_COMMANDS = ("$ST", "$ES 1", "$ES", "$ME", "$AF")
OPTIONAL_READBACKS = ("$GM", "$SX", "$SM", "$FW", "$PH")
_HARD_FAIL = frozenset({"0022", "0110", "0111", "0106", "0112"})


def _emit(text: str, log_fh) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
    log_fh.write(text)
    log_fh.flush()


def _evaluate(command: str, txn) -> tuple[bool, str]:
    if command == "$ST":
        payload = find_status_payload(txn.data_records)
        if payload is None:
            return False, f"no STATUS payload starting with 55; data={txn.data_records!r}"
        try:
            info = parse_status_payload(payload)
        except ValueError as exc:
            return False, str(exc)
        if txn.final_code not in ("0000",) and txn.initial_code == "0110":
            return False, f"busy/initial={txn.initial_code}"
        return True, f"model={info.model} rev={info.revision!r} final={txn.final_code}"

    if command == "$ES 1":
        if txn.final_code in _HARD_FAIL or txn.initial_code in _HARD_FAIL:
            return False, f"hard fail initial={txn.initial_code} final={txn.final_code}"
        return True, f"final={txn.final_code}"

    if command == "$ES":
        if txn.final_code in _HARD_FAIL or txn.initial_code in _HARD_FAIL:
            return False, f"hard fail initial={txn.initial_code} final={txn.final_code}"
        pos = parse_es_position(txn)
        if pos != 1:
            return False, f"expected position 1 (OFF), got {pos!r}"
        return True, f"position={pos}"

    if command == "$ME":
        code = me_status_code(txn)
        if code == "0106":
            return False, "fatal NVM 0106"
        if code == "0108":
            return True, "WARN 0108 (NVM recovered from backup)"
        if code != "0000":
            return False, f"unexpected ME code {code!r}"
        return True, f"me={code}"

    if command == "$AF":
        if txn.final_code in _HARD_FAIL or txn.initial_code in _HARD_FAIL:
            return False, f"hard fail initial={txn.initial_code} final={txn.final_code}"
        bits = txn.data_records[0].strip() if txn.data_records else None
        return True, f"af={bits!r} final={txn.final_code}"

    # Optional readbacks: any completion without hard fail is OK.
    if txn.final_code in _HARD_FAIL:
        return False, f"hard fail final={txn.final_code}"
    return True, f"final={txn.final_code} data={txn.data_records!r}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="LS 55 automated serial comms probe with hex dumps"
    )
    parser.add_argument("--port", required=True, help="Serial device path")
    parser.add_argument("--baud", type=int, default=9600)
    parser.add_argument(
        "--gate-a-pass",
        action="store_true",
        help="Operator sign-off that Gate A safety checks passed",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs" / "stage1",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--skip-optional",
        action="store_true",
        help="Skip parameterless $GM/$SX/$SM/$FW/$PH",
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
    probe_log = args.log_dir / f"probe-{stamp}.log"
    raw_log = args.log_dir / f"probe-{stamp}-raw.log"
    summary_path = args.log_dir / f"probe-{stamp}.json"

    inner = SerialTransport(args.port, baudrate=args.baud, timeout=args.timeout)
    transport = LoggingTransport(inner, raw_log)
    engine = TransactionEngine(transport, timeout_s=args.timeout, prompted=True)

    commands = list(HARD_COMMANDS)
    if not args.skip_optional:
        commands.extend(OPTIONAL_READBACKS)

    results: list[dict] = []
    hard_failed = False

    with probe_log.open("w", encoding="utf-8") as log_fh:
        _emit(
            f"# LS 55 probe {stamp} port={args.port} baud={args.baud}\n",
            log_fh,
        )
        try:
            transport.reset_input_buffer()
            for command in commands:
                _emit(f"\n## {command}\n", log_fh)
                tx = encode_command(command)
                _emit("TX frame:\n", log_fh)
                _emit(hexdump(tx), log_fh)
                try:
                    txn = engine.transact(command)
                    rx = b"".join(r.raw for r in txn.records)
                    _emit("RX records (concatenated):\n", log_fh)
                    _emit(hexdump(rx), log_fh)
                    _emit(
                        f"parsed: initial={txn.initial_code} final={txn.final_code} "
                        f"data={txn.data_records!r}\n",
                        log_fh,
                    )
                    ok, detail = _evaluate(command, txn)
                    status = "PASS" if ok else "FAIL"
                    _emit(f"result: {status} — {detail}\n", log_fh)
                    results.append(
                        {
                            "command": command,
                            "passed": ok,
                            "detail": detail,
                            "initial_code": txn.initial_code,
                            "final_code": txn.final_code,
                            "data": txn.data_records,
                            "rx_hex": rx.hex(),
                        }
                    )
                    if not ok and command in HARD_COMMANDS:
                        hard_failed = True
                except (TimeoutError, ProtocolError) as exc:
                    _emit(f"result: FAIL — {exc}\n", log_fh)
                    results.append(
                        {
                            "command": command,
                            "passed": False,
                            "detail": str(exc),
                        }
                    )
                    if command in HARD_COMMANDS:
                        hard_failed = True
        finally:
            transport.close()

    summary = {
        "passed": not hard_failed,
        "baud": args.baud,
        "port": args.port,
        "probe_log": str(probe_log),
        "raw_log": str(raw_log),
        "commands": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"probe_log={probe_log}", file=sys.stderr)
    print(f"raw_log={raw_log}", file=sys.stderr)
    print(f"summary={summary_path}", file=sys.stderr)
    if hard_failed:
        print("FAIL", file=sys.stderr)
        return 1
    print("PASS", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
