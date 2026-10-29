"""Read-only instrument identity / config fingerprint dump."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import (
    AccessoriesInfo,
    StatusInfo,
    decode_accessories,
    find_status_payload,
    me_status_code,
    parse_es_position,
    parse_status_payload,
)
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine

# Safe read-only queries after source-OFF confirm. No motion setpoints, no
# calibration, no $PV override write, no $RE 0.
IDENTITY_READBACKS = (
    "$SN",
    "$HZ",
    "$PV",
    "$CX",
    "$PT",
    "$TP",
    "$GM",
    "$SX",
    "$SM",
    "$FW",
    "$PH",
)

_HARD_FAIL_CODES = frozenset({"0022", "0110", "0112"})


@dataclass
class IdentityResult:
    ok: bool
    gate_a_pass: bool
    compartment_closed: bool
    status: Optional[dict[str, Any]] = None
    status_raw: Optional[str] = None
    es_position: Optional[int] = None
    me_code: Optional[str] = None
    accessories: Optional[dict[str, Any]] = None
    af_bits: Optional[str] = None
    readbacks: dict[str, Any] = field(default_factory=dict)
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


def _status_to_dict(info: StatusInfo) -> dict[str, Any]:
    return {
        "model": info.model,
        "revision": info.revision,
        "ms": info.ms,
        "mq": info.mq,
        "dc": info.dc,
        "fl": info.fl,
        "ex_nm": info.ex_nm,
        "em_nm": info.em_nm,
        "speed": info.speed,
        "response": info.response,
        "ex_slit": info.ex_slit,
        "em_slit": info.em_slit,
        "gate_ms": info.gate_ms,
        "delay_ms": info.delay_ms,
        "flashcount": info.flashcount,
        "cycle_ms": info.cycle_ms,
        "fields": info.fields,
    }


def _accessories_to_dict(info: AccessoriesInfo) -> dict[str, Any]:
    return {
        "raw": info.raw,
        "flags": info.flags,
        "fitted": [name for name, on in info.flags.items() if on],
        "extra_bits": info.extra_bits,
    }


def run_identity_dump(
    engine: TransactionEngine,
    *,
    gate_a_pass: bool,
    compartment_closed: bool,
) -> IdentityResult:
    """
    Prompted-mode identity dump:

      confirm/force $ES OFF → $ST → $ME → $AF → identity readbacks.
    """
    result = IdentityResult(
        ok=False,
        gate_a_pass=gate_a_pass,
        compartment_closed=compartment_closed,
    )
    if not gate_a_pass:
        result.errors.append("Gate A not signed off; refusing identity dump")
        return result
    if not compartment_closed:
        result.errors.append("Compartment not confirmed closed; refusing identity dump")
        return result

    try:
        # Source OFF first.
        es_set = engine.transact("$ES 1")
        result.transactions.append(_txn_summary(es_set))
        if es_set.initial_code in _HARD_FAIL_CODES or es_set.final_code in _HARD_FAIL_CODES:
            result.errors.append(
                f"$ES 1 hard-fail code initial={es_set.initial_code} final={es_set.final_code}"
            )
            return result

        es = engine.transact("$ES")
        result.transactions.append(_txn_summary(es))
        result.es_position = parse_es_position(es)
        if result.es_position != 1:
            result.errors.append(f"$ES readback is {result.es_position!r}, expected 1 (OFF)")
            return result

        st = engine.transact("$ST")
        result.transactions.append(_txn_summary(st))
        if st.initial_code in _HARD_FAIL_CODES or st.final_code in _HARD_FAIL_CODES:
            result.errors.append(
                f"$ST hard-fail initial={st.initial_code} final={st.final_code}"
            )
            return result
        payload = find_status_payload(st.data_records)
        if payload is None:
            result.errors.append(
                f"$ST missing status data starting with 55; got {st.data_records!r}"
            )
            return result
        result.status_raw = payload
        info = parse_status_payload(payload)
        result.status = _status_to_dict(info)

        me = engine.transact("$ME")
        result.transactions.append(_txn_summary(me))
        result.me_code = me_status_code(me)
        if result.me_code == "0106":
            result.errors.append("$ME = 0106 fatal NVM")
            return result
        if result.me_code == "0108":
            result.warnings.append("$ME = 0108 NVM recovered from backup")
        elif result.me_code not in {"0000", None}:
            result.warnings.append(f"$ME unexpected code {result.me_code!r}")

        af = engine.transact("$AF")
        result.transactions.append(_txn_summary(af))
        if af.data_records:
            result.af_bits = af.data_records[0]
            result.accessories = _accessories_to_dict(decode_accessories(result.af_bits))
        else:
            result.warnings.append("$AF returned no accessory data record")

        for cmd in IDENTITY_READBACKS:
            try:
                txn = engine.transact(cmd)
            except (TimeoutError, ProtocolError) as exc:
                result.warnings.append(f"{cmd} failed: {exc}")
                result.readbacks[cmd] = {"error": str(exc)}
                continue
            result.transactions.append(_txn_summary(txn))
            entry: dict[str, Any] = {
                "initial_code": txn.initial_code,
                "final_code": txn.final_code,
                "data": txn.data_records,
            }
            if txn.final_code in _HARD_FAIL_CODES or txn.initial_code in _HARD_FAIL_CODES:
                result.warnings.append(
                    f"{cmd} hard-fail-ish code initial={txn.initial_code} final={txn.final_code}"
                )
            # $PT / $TP often complete as a single status code (0100 / 0107 / 0000).
            if cmd == "$PT" and txn.final_code == "0107":
                result.warnings.append("$PT latched PMT over-range (0107)")
            if cmd == "$TP" and txn.final_code == "0100":
                entry["note"] = "no temperature sensor / invalid parameter (0100)"
            result.readbacks[cmd] = entry

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result

    result.ok = not result.errors
    return result
