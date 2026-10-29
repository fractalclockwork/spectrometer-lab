"""Serial and fake transports for LS 55 Stage-1 harness."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class Transport(Protocol):
    def write(self, data: bytes) -> None: ...

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


class SerialTransport:
    """pySerial wrapper with Stage-1 settings (default 9600 8N1, no host XON/XOFF)."""

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout: float = 0.05,
        write_timeout: float = 2.0,
    ) -> None:
        try:
            import serial
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "pyserial is required for live Stage-1 runs; pip install -r requirements.txt"
            ) from exc

        self.baudrate = baudrate
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout,
            write_timeout=write_timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
            exclusive=True,
        )
        self.reset_input_buffer()

    def reset_input_buffer(self) -> None:
        self._ser.reset_input_buffer()

    def write(self, data: bytes) -> None:
        self._ser.write(data)
        self._ser.flush()

    def read(self, size: int = 1) -> bytes:
        return self._ser.read(size)

    def close(self) -> None:
        self._ser.close()


class LoggingTransport:
    """Wrap a transport and append timestamped TX/RX lines to a log file."""

    def __init__(self, inner: Transport, log_path: Path) -> None:
        self._inner = inner
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._log_path.open("a", encoding="utf-8")

    def _stamp(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + f".{int(time.time() % 1 * 1000):03d}"

    def _emit(self, direction: str, data: bytes) -> None:
        hex_part = data.hex(" ")
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
        self._fh.write(f"{self._stamp()} {direction} hex={hex_part} ascii={ascii_part!r}\n")
        self._fh.flush()

    def reset_input_buffer(self) -> None:
        reset = getattr(self._inner, "reset_input_buffer", None)
        if callable(reset):
            reset()

    def write(self, data: bytes) -> None:
        self._emit("TX", data)
        self._inner.write(data)

    def read(self, size: int = 1) -> bytes:
        data = self._inner.read(size)
        if data:
            self._emit("RX", data)
        return data

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            self._fh.close()


class FakeTransport:
    """
    Prompted-mode instrument simulator.

    Fixture JSON schema (tests/fixtures/<case>/script.json):
      {
        "commands": {
          "$ST": ["0000\\r\\n", "\\x7f55,A1,...\\r\\n", "0000\\r\\n"],
          ...
        },
        "fragment_sizes": [1]   # optional; default whole-record reads
      }

    On write of a CR-terminated command, response records are queued.
    On write of DC1 (0x11), the next queued record is released to the read buffer.
    """

    def __init__(
        self,
        command_map: dict[str, list[bytes] | list[list[bytes]]],
        *,
        fragment_size: Optional[int] = None,
        read_timeout_empty: bool = False,
    ) -> None:
        # Values are either a flat record list, or a queue of record lists
        # (each queue entry consumed once per matching command).
        self._command_map: dict[str, list] = {
            k.upper(): v for k, v in command_map.items()
        }
        self._fragment_size = fragment_size
        self._read_timeout_empty = read_timeout_empty
        self._pending_records: list[bytes] = []
        self._rx = bytearray()
        self._cmd_buf = bytearray()
        self.writes: list[bytes] = []

    @classmethod
    def from_fixture_dir(cls, path: Path) -> "FakeTransport":
        script_path = path / "script.json"
        data = json.loads(script_path.read_text(encoding="utf-8"))
        commands: dict[str, list] = {}
        for key, records in data.get("commands", {}).items():
            if isinstance(records, dict) and "queue" in records:
                commands[key] = [
                    [_decode_fixture_record(r) for r in entry]
                    for entry in records["queue"]
                ]
            else:
                commands[key] = [_decode_fixture_record(r) for r in records]
        fragment = data.get("fragment_size")
        return cls(
            commands,
            fragment_size=fragment,
            read_timeout_empty=bool(data.get("read_timeout_empty", False)),
        )

    def write(self, data: bytes) -> None:
        self.writes.append(data)
        for byte in data:
            b = bytes([byte])
            if b == b"\x11":  # DC1
                self._release_one_record()
                continue
            if b == b"\x13":  # DC3 ignored in prompted (already prompted)
                continue
            self._cmd_buf.append(byte)
            if byte == 0x0D:  # CR ends command
                self._accept_command(bytes(self._cmd_buf))
                self._cmd_buf.clear()

    def _accept_command(self, framed: bytes) -> None:
        body = framed.rstrip(b"\r\n").decode("ascii", errors="replace").strip().upper()
        entry = self._command_map.get(body)
        if entry is None:
            entry = self._command_map.get("__DEFAULT__")
        if entry is None:
            self._pending_records.extend([b"0002\r\n"])
            return
        # Queued responses: list of record-lists (first element is itself a list).
        if entry and isinstance(entry[0], list):
            records = entry.pop(0)
            if not entry:
                # Keep last response sticky for further identical readbacks.
                entry.append(list(records))
            self._pending_records.extend(records)
            return
        self._pending_records.extend(list(entry))

    def _release_one_record(self) -> None:
        if not self._pending_records:
            return
        record = self._pending_records.pop(0)
        if self._fragment_size and self._fragment_size > 0:
            # Still place full record in buffer; read() will fragment.
            self._rx.extend(record)
        else:
            self._rx.extend(record)

    def read(self, size: int = 1) -> bytes:
        if self._read_timeout_empty and not self._rx:
            return b""
        if not self._rx:
            return b""
        n = size
        if self._fragment_size:
            n = min(n, self._fragment_size, len(self._rx))
        else:
            n = min(n, len(self._rx))
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def close(self) -> None:
        return


def _decode_fixture_record(value: str | list[int]) -> bytes:
    """Accept a JSON string with \\x escapes or a list of byte ints."""
    if isinstance(value, list):
        return bytes(value)
    # json already unescapes \\r \\n \\u007f; also support literal \x7f in file via unicode
    return value.encode("latin-1")
