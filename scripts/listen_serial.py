#!/usr/bin/env python3
"""Raw listen / optional TX helper for LS 55 link triage (boot capture, scope correlate)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Listen on LS 55 serial port; optionally send a CR-terminated command"
    )
    parser.add_argument(
        "--port",
        required=True,
        help="Serial device (prefer /dev/serial/by-id/...)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=9600,
        help="Baud rate (default 9600; set from scope bit-time measurement if not 9600)",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=15.0,
        help="How long to listen (default 15)",
    )
    parser.add_argument(
        "--send",
        default="",
        help="Optional command body without terminator, e.g. '$ST' or '$ST' then DC1 via --dc1",
    )
    parser.add_argument(
        "--dc1",
        action="store_true",
        help="After --send, also transmit DC1 (0x11) once",
    )
    parser.add_argument(
        "--assert-dtr",
        action="store_true",
        help="Assert DTR (and RTS) after open",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Append hex/ascii RX/TX log path (default logs/stage1/listen-*.log)",
    )
    args = parser.parse_args(argv)

    import serial

    log_dir = REPO_ROOT / "logs" / "stage1"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log or (log_dir / f"listen-{time.strftime('%Y%m%d-%H%M%S')}.log")

    ser = serial.Serial(
        port=args.port,
        baudrate=args.baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.05,
        write_timeout=2.0,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
        exclusive=True,
    )
    if args.assert_dtr:
        ser.dtr = True
        ser.rts = True

    def emit(direction: str, data: bytes) -> None:
        hex_part = data.hex(" ")
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
        line = f"{time.strftime('%H:%M:%S')} {direction} hex={hex_part} ascii={ascii_part!r}\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    total = bytearray()
    try:
        ser.reset_input_buffer()
        print(
            f"listening {args.seconds}s on {args.port} at {args.baud} baud; "
            f"power-cycle, press MPU reset, or await reply. log={log_path}",
            file=sys.stderr,
        )
        if args.send:
            frame = args.send.encode("ascii")
            if not frame.endswith(b"\r"):
                frame += b"\r"
            ser.write(frame)
            ser.flush()
            emit("TX", frame)
            if args.dc1:
                ser.write(b"\x11")
                ser.flush()
                emit("TX", b"\x11")

        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            chunk = ser.read(256)
            if chunk:
                total.extend(chunk)
                emit("RX", chunk)
        print(
            f"done: {len(total)} byte(s) captured. hex={total.hex(' ')!r}",
            file=sys.stderr,
        )
    finally:
        ser.close()
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
