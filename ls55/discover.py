"""Device discovery and power-on readiness for the LS 55."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ls55.protocol import (
    find_status_payload,
    parse_es_position,
    parse_status_payload,
)
from ls55.source import SOURCE_ON, ensure_source_off
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine

_HARD_FAIL_CODES = frozenset({"0022", "0112"})


@dataclass
class DiscoverResult:
    """Outcome of a discovery / readiness probe."""

    ready: bool
    state: str  # ready | busy | booting | error | no_device
    gate_a_pass: bool
    port: Optional[str] = None
    job_running: bool = False
    first_power_on: bool = False
    lamp_disabled: bool = False
    es_position_initial: Optional[int] = None
    es_position: Optional[int] = None
    status_model: Optional[str] = None
    status_revision: Optional[str] = None
    status_raw: Optional[str] = None
    boot_attempts: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _txn_summary(txn) -> dict[str, Any]:
    return {
        "command": txn.command,
        "initial_code": txn.initial_code,
        "final_code": txn.final_code,
        "data": txn.data_records,
        "raw_records": [r.raw.hex() for r in txn.records],
    }


def list_candidate_ports() -> list[str]:
    """
    List USB–serial candidates for the LS 55.

    Prefer stable ``/dev/serial/by-id`` symlinks. If that directory is absent
    or empty (adapter unplugged), do **not** fall back to platform UARTs
    (``/dev/ttyS*``) — those are not the DUT adapter and caused false
    "adapter up" badges.
    """
    by_id = Path("/dev/serial/by-id")
    if by_id.is_dir():
        return sorted(
            str(p) for p in by_id.iterdir() if p.exists() and not p.name.startswith(".")
        )

    try:
        from serial.tools import list_ports
    except ImportError:  # pragma: no cover
        return []

    usb_ports: list[str] = []
    for p in list_ports.comports():
        if not p.device:
            continue
        # USB adapters only (VID present, ttyUSB/ttyACM, or USB in hwid).
        hwid = (p.hwid or "").upper()
        if (
            p.vid is not None
            or p.device.startswith(("/dev/ttyUSB", "/dev/ttyACM"))
            or "USB" in hwid
        ):
            usb_ports.append(p.device)
    return sorted(set(usb_ports))


def run_discover(
    engine: TransactionEngine,
    *,
    gate_a_pass: bool,
    port: Optional[str] = None,
    boot_wait_s: float = 90.0,
    boot_poll_s: float = 2.0,
    force_idle_source_off: bool = True,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> DiscoverResult:
    """
    Probe instrument status and optionally enforce Xe OFF as the idle resting state.

    Sequence:
      1. Poll ``$ST`` until response, busy, or boot deadline.
      2. If ``0110``, report busy and leave the shutter alone (do not abort jobs).
      3. When idle: either read ``$ES`` only (status probe) or ``ensure_source_off``
         (``$ES 1`` + verify) for Connect / safe-idle sessions.
    """
    result = DiscoverResult(ready=False, state="error", gate_a_pass=gate_a_pass, port=port)
    if not gate_a_pass:
        result.errors.append("Gate A not signed off; refusing discovery")
        return result

    try:
        st = _wait_for_status(
            engine,
            result,
            boot_wait_s=boot_wait_s,
            boot_poll_s=boot_poll_s,
            sleep=sleep,
            monotonic=monotonic,
        )
        if st is None:
            return result

        if st.initial_code == "0110":
            result.state = "busy"
            result.job_running = True
            result.errors.append("busy 0110 on $ST; leaving excitation shutter unchanged")
            return result
        if st.initial_code in _HARD_FAIL_CODES or st.final_code in _HARD_FAIL_CODES:
            result.errors.append(
                f"$ST hard-fail initial={st.initial_code} final={st.final_code}"
            )
            return result
        if st.initial_code != "0000" or st.final_code != "0000":
            result.errors.append(
                f"$ST unexpected codes initial={st.initial_code} final={st.final_code}"
            )
            return result

        payload = find_status_payload(st.data_records)
        if payload is None:
            result.errors.append(
                f"$ST missing status data starting with 55; got {st.data_records!r}"
            )
            return result
        info = parse_status_payload(payload)
        result.status_raw = info.raw_payload
        result.status_model = info.model
        result.status_revision = info.revision
        if info.model != "55":
            result.errors.append(f"unexpected model {info.model!r}; expected '55'")
            return result

        if not force_idle_source_off:
            # Read-only classify for dashboard Probe — do not change shutter.
            es = engine.transact("$ES")
            result.transactions.append(_txn_summary(es))
            pos = parse_es_position(es)
            result.es_position_initial = pos
            result.es_position = pos
            result.first_power_on = pos == SOURCE_ON
            result.lamp_disabled = False
            if pos is None:
                result.errors.append("$ES readback missing during read-only probe")
                return result
            result.state = "ready"
            result.ready = True
            return result

        # Resting policy: Xe / excitation shutter OFF whenever the host opens a session.
        off = ensure_source_off(engine)
        result.transactions.extend(off.transactions)
        result.es_position_initial = off.es_before
        result.es_position = off.es_after
        result.first_power_on = off.was_on
        result.lamp_disabled = off.was_on and off.ok
        if off.busy:
            result.state = "busy"
            result.job_running = True
            result.errors.extend(off.errors)
            return result
        if not off.ok:
            result.errors.extend(off.errors)
            return result

        result.state = "ready"
        result.ready = True
        return result

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result
    except ValueError as exc:
        result.errors.append(str(exc))
        return result


def _wait_for_status(
    engine: TransactionEngine,
    result: DiscoverResult,
    *,
    boot_wait_s: float,
    boot_poll_s: float,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
):
    """Poll ``$ST`` through boot silence; return the transaction or None."""
    deadline = monotonic() + boot_wait_s
    while True:
        result.boot_attempts += 1
        try:
            st = engine.transact("$ST")
        except TimeoutError as exc:
            if monotonic() >= deadline:
                result.state = "booting"
                result.errors.append(
                    f"no $ST response within {boot_wait_s:.0f}s boot window ({exc})"
                )
                return None
            result.warnings.append(f"boot poll timeout attempt {result.boot_attempts}: {exc}")
            remaining = deadline - monotonic()
            sleep(min(boot_poll_s, max(0.0, remaining)))
            continue

        result.transactions.append(_txn_summary(st))
        return st
