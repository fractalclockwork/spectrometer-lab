#!/usr/bin/env python3
"""Mine logs/ for Class A (STATUS 0x01) and Class B (0xb5) serial anomalies.

Offline only. Prints a markdown-friendly summary for docs/issues/serial-link-glitch-taxonomy.md.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEL = 0x7F
B5 = 0xB5
SOH = 0x01


@dataclass
class Findings:
    class_a_status: list[str] = field(default_factory=list)
    class_a_offsets: Counter = field(default_factory=Counter)
    b_modes: Counter = field(default_factory=Counter)
    b_by_command: Counter = field(default_factory=Counter)
    b_events: list[str] = field(default_factory=list)
    files_scanned: int = 0
    json_txns: int = 0


def _classify_b5_in_record(raw: bytes) -> str | None:
    """Return Class B mode label if 0xb5 appears in a record."""
    if B5 not in raw:
        return None

    # CR replaced by 0xb5 before LF: …\xb5\n
    if raw.endswith(b"\xb5\n") and not raw.endswith(b"\xb5\r\n"):
        return "B3_cr_replaced"

    body = raw
    if body.endswith(b"\r\n"):
        body = body[:-2]
    elif body.endswith(b"\n") or body.endswith(b"\r"):
        body = body[:-1]

    if not body:
        return "B_other"

    # Leading junk before a 4-digit code.
    if body[0] == B5 and len(body) >= 5 and body[1:5].isdigit():
        return "B1_leading_junk"

    # 4-byte code with one high byte + three digits.
    if len(body) == 4:
        high = sum(1 for b in body if b >= 0x80)
        digits = sum(1 for b in body if 0x30 <= b <= 0x39)
        if high >= 1 and digits == 3:
            return "B2_mid_code_digit"
        if high >= 1 and digits + high == 4:
            return "B2_mid_code_digit"

    # DEL-prefixed data.
    if body[:1] == bytes([DEL]):
        data = body[1:]
        if data == bytes([B5]):
            return "B6_sole_ph_data"
        if B5 in data:
            idx = data.index(B5)
            before = data[idx - 1] if idx > 0 else None
            after = data[idx + 1] if idx + 1 < len(data) else None
            if before in (0x30, 0x31) and after in (0x30, 0x31):
                return "B4_data_comma"
            if (
                before is not None
                and 0x30 <= before <= 0x39
                and after is not None
                and (0x30 <= after <= 0x39 or after == 0x2E)
            ):
                return "B5_data_digit"
            return "B_data_other"

    return "B_other"


def analyze(log_dir: Path) -> Findings:
    findings = Findings()
    for path in sorted(log_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        findings.files_scanned += 1
        # Error / cleanup strings may hold B3 partials never stored as raw_records.
        # After json.loads, freepath cleanup stores the repr text ``0000\xb5\n``.
        def _walk_strings(obj) -> bool:
            if isinstance(obj, str):
                return r"0000\xb5\n" in obj or "0000\xb5\n" in obj
            if isinstance(obj, dict):
                return any(_walk_strings(v) for v in obj.values())
            if isinstance(obj, list):
                return any(_walk_strings(v) for v in obj)
            return False

        if _walk_strings(data):
            findings.b_modes["B3_cr_replaced"] += 1
            findings.b_events.append(f"{path.name}:?:B3_cr_replaced:from_error_string")
        for txn in data.get("transactions") or []:
            findings.json_txns += 1
            cmd = str(txn.get("command") or "?")
            for hexrec in txn.get("raw_records") or []:
                try:
                    raw = bytes.fromhex(hexrec)
                except ValueError:
                    continue

                is_status = (
                    len(raw) > 10
                    and raw[0] == DEL
                    and (raw.startswith(b"\x7f55.") or raw.startswith(b"\x7f55,"))
                )
                if is_status and SOH in raw:
                    off = raw.index(SOH)
                    findings.class_a_offsets[off] += 1
                    findings.class_a_status.append(f"{path.name}:{cmd}:offset={off}")

                mode = _classify_b5_in_record(raw)
                if mode:
                    findings.b_modes[mode] += 1
                    findings.b_by_command[cmd] += 1
                    findings.b_events.append(f"{path.name}:{cmd}:{mode}:{raw.hex()}")

    for path in sorted(log_dir.rglob("*.log")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n = sum(1 for line in text.splitlines() if re.search(r"RX hex=b5\b", line))
        if n:
            findings.b_modes["B_rx_line_log"] += n
    return findings


def format_report(findings: Findings) -> str:
    lines: list[str] = [
        "# Serial glitch analysis (auto)",
        "",
        f"- JSON files / transactions scanned: {findings.files_scanned} / {findings.json_txns}",
        "",
        "## Class A — STATUS `0x01` (flashcount)",
        "",
        f"- STATUS records with embedded `0x01`: **{len(findings.class_a_status)}**",
    ]
    if findings.class_a_offsets:
        lines.append("- Byte offsets (within full DEL-prefixed record):")
        for off, n in sorted(findings.class_a_offsets.items()):
            mark = " (canonical)" if off == 57 else ""
            lines.append(f"  - offset {off}: {n}{mark}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Class B — intermittent `0xb5` (from JSON raw_records)", ""])
    mode_rows = [(k, v) for k, v in sorted(findings.b_modes.items()) if k != "B_rx_line_log"]
    if not mode_rows:
        lines.append("- (none)")
    else:
        lines.append("| Mode | Count |")
        lines.append("| --- | ---: |")
        for k, v in mode_rows:
            lines.append(f"| `{k}` | {v} |")

    rx_lines = findings.b_modes.get("B_rx_line_log", 0)
    lines.extend(
        [
            "",
            f"- Raw-log standalone `RX hex=b5` lines (byte-wise logging): **{rx_lines}**",
            "",
            "## Class B by command",
            "",
        ]
    )
    if not findings.b_by_command:
        lines.append("- (none)")
    else:
        lines.append("| Command | `0xb5` events |")
        lines.append("| --- | ---: |")
        for cmd, n in findings.b_by_command.most_common():
            lines.append(f"| `{cmd}` | {n} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=REPO_ROOT / "logs",
        help="Root of captured logs (default: logs/)",
    )
    args = parser.parse_args(argv)
    print(format_report(analyze(args.log_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
