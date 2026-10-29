"""Prompted-mode transaction engine: one outstanding command, DC1 pacing."""

from __future__ import annotations

import time

from ls55.protocol import DC1, CRLF, Record, Transaction, encode_command
from ls55.transport import Transport


class ProtocolError(Exception):
    """Framing or completion failure."""


class TimeoutError(ProtocolError):
    """No complete record within the configured timeout."""


def _idle_success_codes_only(txn: Transaction) -> bool:
    if txn.data_records:
        return False
    codes = [r for r in txn.records if r.is_code]
    return bool(codes) and all(c.code == "0000" for c in codes)


def _success_code_count(txn: Transaction) -> int:
    if txn.data_records:
        return 0
    return sum(1 for r in txn.records if r.is_code and r.code == "0000")


class TransactionEngine:
    """
    Serialize commands. In prompted mode, after each command send DC1 and
    read CR+LF records until Transaction.complete.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        timeout_s: float = 5.0,
        inter_byte_timeout_s: float = 2.0,
        prompted_idle_s: float = 0.2,
        prompted: bool = True,
    ) -> None:
        self._transport = transport
        self._timeout_s = timeout_s
        self._inter_byte_timeout_s = inter_byte_timeout_s
        self._prompted_idle_s = prompted_idle_s
        self._prompted = prompted
        self._busy = False

    def transact(
        self,
        command: str,
        *,
        idle_complete: bool = True,
        timeout_s: float | None = None,
    ) -> Transaction:
        """
        Run one command to completion.

        idle_complete: if True, a short RX idle after success code(s) with no
        data ends the transaction (e.g. $ES 1). Set False for long motions
        ($GM/$SX/$SM with parameters) so the first 0000 is not mistaken for done.
        timeout_s: optional per-call override of the engine default timeout.
        """
        if self._busy:
            raise ProtocolError("overlapping command (internal serialization fault)")
        self._busy = True
        try:
            frame = encode_command(command)
            self._transport.write(frame)
            txn = Transaction(command=command if command.startswith("$") else f"${command}")
            overall_timeout = self._timeout_s if timeout_s is None else timeout_s
            deadline = time.monotonic() + overall_timeout

            while not txn.complete:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"timeout waiting for completion of {txn.command}; "
                        f"got {len(txn.records)} record(s)"
                    )
                if self._prompted:
                    self._transport.write(DC1)
                # After success code(s) with no data, a short idle means the
                # instrument has no further records (e.g. $ES 1 → 0000).
                # For motion (idle_complete=False), require ≥2 success codes
                # before short-idle completion so an early accept 0000 is not
                # mistaken for done; a lone 0000 may still finish at deadline.
                record_deadline = deadline
                allow_idle = idle_complete or _success_code_count(txn) >= 2
                if allow_idle and _idle_success_codes_only(txn):
                    record_deadline = min(
                        deadline, time.monotonic() + self._prompted_idle_s
                    )
                try:
                    record = self._read_record(record_deadline)
                except TimeoutError:
                    if _idle_success_codes_only(txn):
                        if allow_idle or time.monotonic() >= deadline:
                            break
                    raise
                txn.records.append(record)
            return txn
        finally:
            self._busy = False

    def _read_record(self, deadline: float) -> Record:
        buf = bytearray()
        last_byte_at = time.monotonic()
        while True:
            now = time.monotonic()
            if now > deadline:
                raise TimeoutError(f"timeout reading record; partial={bytes(buf)!r}")
            if buf and (now - last_byte_at) > self._inter_byte_timeout_s:
                raise TimeoutError(f"inter-byte timeout; partial={bytes(buf)!r}")

            chunk = self._transport.read(1)
            if not chunk:
                time.sleep(0.001)
                if not buf and time.monotonic() > deadline:
                    raise TimeoutError("timeout with empty read")
                continue

            last_byte_at = time.monotonic()
            buf.extend(chunk)
            if bytes(buf).endswith(CRLF):
                return Record.parse(bytes(buf))
            # Live glitch: CR replaced by a high byte (e.g. 0xb5) before LF.
            if len(buf) >= 2 and buf[-1] == 0x0A and buf[-2] >= 0x80:
                fixed = bytes(buf[:-2]) + CRLF
                return Record.parse(fixed)
            if len(buf) > 256:
                raise ProtocolError(f"record exceeds max length: {bytes(buf)!r}")
