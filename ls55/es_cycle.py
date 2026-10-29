"""Bounded excitation-shutter ($ES) on/off cycle. Always ends source OFF."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import parse_es_position
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine


def _txn_summary(txn) -> dict[str, Any]:
    return {
        "command": txn.command,
        "initial_code": txn.initial_code,
        "final_code": txn.final_code,
        "data": txn.data_records,
        "raw_records": [r.raw.hex() for r in txn.records],
    }


@dataclass
class EsCycleResult:
    passed: bool
    before: Optional[int] = None
    after_on: Optional[int] = None
    after_off: Optional[int] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_es_cycle(
    engine: TransactionEngine,
    *,
    compartment_closed: bool,
    on_dwell_s: float = 2.0,
) -> EsCycleResult:
    """
    Read $ES → $ES 0 (ON) → readback 0 → dwell → $ES 1 (OFF) → readback 1.

    Polarity (User’s Guide): 0 = source ON, 1 = source OFF.
    """
    import time

    result = EsCycleResult(passed=False)
    if not compartment_closed:
        result.errors.append(
            "refusing: pass compartment_closed=True / --compartment-closed "
            "(door shut, empty, no beam viewing)"
        )
        return result

    try:
        es0 = engine.transact("$ES")
        result.transactions.append(_txn_summary(es0))
        result.before = parse_es_position(es0)
        if result.before is None:
            result.errors.append("$ES readback missing before cycle")
            return result

        on = engine.transact("$ES 0")
        result.transactions.append(_txn_summary(on))
        es_on = engine.transact("$ES")
        result.transactions.append(_txn_summary(es_on))
        result.after_on = parse_es_position(es_on)
        if result.after_on != 0:
            result.errors.append(
                f"$ES 0 did not yield ON readback (got {result.after_on!r})"
            )
            # Still attempt OFF below.

        if on_dwell_s > 0:
            time.sleep(on_dwell_s)

    except (TimeoutError, ProtocolError) as exc:
        result.errors.append(f"during ON path: {exc}")

    # Always attempt OFF, even if ON path failed.
    try:
        off = engine.transact("$ES 1")
        result.transactions.append(_txn_summary(off))
        es_off = engine.transact("$ES")
        result.transactions.append(_txn_summary(es_off))
        result.after_off = parse_es_position(es_off)
        if result.after_off != 1:
            result.errors.append(
                f"$ES 1 did not yield OFF readback (got {result.after_off!r}); "
                "treat source as UNKNOWN — do not open compartment"
            )
    except (TimeoutError, ProtocolError) as exc:
        result.errors.append(
            f"OFF path failed: {exc}; treat source as UNKNOWN — do not open compartment"
        )
        return result

    result.passed = len(result.errors) == 0 and result.after_on == 0 and result.after_off == 1
    return result
