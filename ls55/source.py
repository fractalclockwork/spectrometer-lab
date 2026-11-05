"""Excitation-source (Xe / ``$ES``) helpers. Resting default is OFF."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import parse_es_position
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine

# Polarity (User's Guide): 0 = source ON, 1 = source OFF.
SOURCE_ON = 0
SOURCE_OFF = 1

_HARD_FAIL = frozenset({"0022", "0110", "0112"})


@dataclass
class SourceOffResult:
    """Result of forcing the excitation shutter to the OFF resting state."""

    ok: bool
    es_before: Optional[int] = None
    es_after: Optional[int] = None
    was_on: bool = False
    commanded: bool = False
    busy: bool = False
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


def _is_hard(code: Optional[str]) -> bool:
    return code in _HARD_FAIL


def _flush_rx(engine: TransactionEngine) -> None:
    transport = getattr(engine, "_transport", None)
    reset = getattr(transport, "reset_input_buffer", None)
    if callable(reset):
        try:
            reset()
        except Exception:  # pragma: no cover - best-effort link hygiene
            pass


def ensure_source_off(engine: TransactionEngine) -> SourceOffResult:
    """
    Make Xe / excitation shutter OFF the resting state.

    Always issues ``$ES 1`` and verifies readback ``1``, so callers can treat
    success as "source is confirmed OFF" (lamp life + acoustic quiet).

    If the first ``$ES`` query returns ``0022`` (UART glitch), empty/garbled
    position data, or other recoverable noise (seen after fault / power-on),
    flush RX, send ``$AB`` once, and retry the query.
    """
    result = SourceOffResult(ok=False)
    try:
        es_get = engine.transact("$ES")
        result.transactions.append(_txn_summary(es_get))
        hard = _is_hard(es_get.initial_code) or _is_hard(es_get.final_code)
        if hard and (es_get.initial_code == "0110" or es_get.final_code == "0110"):
            result.errors.append(
                f"$ES query failed initial={es_get.initial_code} final={es_get.final_code}"
            )
            result.busy = True
            return result
        if hard and (es_get.initial_code == "0112" or es_get.final_code == "0112"):
            result.errors.append(
                f"$ES query failed initial={es_get.initial_code} final={es_get.final_code}"
            )
            return result

        before = parse_es_position(es_get)
        need_retry = (
            before not in (SOURCE_ON, SOURCE_OFF)
            or es_get.initial_code == "0022"
            or es_get.final_code == "0022"
        )
        if need_retry:
            # UART glitch / empty readback: clear dialogue then re-query once.
            _flush_rx(engine)
            try:
                ab = engine.transact("$AB")
                result.transactions.append(_txn_summary(ab))
                result.warnings.append(
                    f"$ES recover ({before!r}, codes {es_get.initial_code}/{es_get.final_code}); "
                    f"$AB → {ab.final_code or ab.initial_code}"
                )
            except (TimeoutError, ProtocolError) as exc:
                result.warnings.append(f"$AB before $ES retry: {exc}")
            es_get = engine.transact("$ES")
            result.transactions.append(_txn_summary(es_get))
            if _is_hard(es_get.initial_code) or _is_hard(es_get.final_code):
                result.errors.append(
                    f"$ES retry failed initial={es_get.initial_code} final={es_get.final_code}"
                )
                if es_get.initial_code == "0110" or es_get.final_code == "0110":
                    result.busy = True
                return result
            before = parse_es_position(es_get)

        result.es_before = before
        if before not in (SOURCE_ON, SOURCE_OFF):
            result.errors.append(f"$ES readback is {before!r}, expected 0 or 1")
            return result
        result.was_on = before == SOURCE_ON

        es_set = engine.transact("$ES 1")
        result.transactions.append(_txn_summary(es_set))
        result.commanded = True
        if _is_hard(es_set.initial_code) or _is_hard(es_set.final_code):
            result.errors.append(
                f"$ES 1 failed initial={es_set.initial_code} final={es_set.final_code}"
            )
            if es_set.initial_code == "0110" or es_set.final_code == "0110":
                result.busy = True
            return result

        es_verify = engine.transact("$ES")
        result.transactions.append(_txn_summary(es_verify))
        after = parse_es_position(es_verify)
        result.es_after = after
        if after != SOURCE_OFF:
            result.errors.append(
                f"$ES readback after OFF is {after!r}, expected {SOURCE_OFF}"
            )
            return result

        result.ok = True
        return result

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result
