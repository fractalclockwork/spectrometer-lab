"""Stage-1 power-on / serial system check sequence and pass/fail evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import (
    find_status_payload,
    me_status_code,
    parse_es_position,
    parse_status_payload,
)
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine


OPTIONAL_READBACKS = ("$GM", "$SX", "$SM", "$FW", "$PH")
_HARD_FAIL_CODES = frozenset({"0022", "0110", "0111", "0106", "0112"})


def _hard_fail_code(code: Optional[str]) -> bool:
    return code in _HARD_FAIL_CODES


@dataclass
class Stage1Result:
    passed: bool
    gate_a_pass: bool
    status_model: Optional[str] = None
    status_revision: Optional[str] = None
    status_raw: Optional[str] = None
    es_position: Optional[int] = None
    me_code: Optional[str] = None
    af_bits: Optional[str] = None
    optional_readbacks: dict[str, Any] = field(default_factory=dict)
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


def run_stage1(
    engine: TransactionEngine,
    *,
    gate_a_pass: bool,
    include_optional_readbacks: bool = True,
) -> Stage1Result:
    """
    Execute Stage-1 sequence in prompted mode:
      $ST → $ES 1 → $ES → $ME → $AF → optional settings readbacks.
    """
    result = Stage1Result(passed=False, gate_a_pass=gate_a_pass)
    if not gate_a_pass:
        result.errors.append("Gate A not signed off; refusing to run Stage 1")
        return result

    try:
        # 1. STATUS
        st = engine.transact("$ST")
        result.transactions.append(_txn_summary(st))
        if st.initial_code == "0022":
            result.errors.append("framing error 0022 on $ST")
            return result
        if st.initial_code == "0110":
            result.errors.append("busy 0110 on $ST")
            return result
        if st.initial_code != "0000" or st.final_code != "0000":
            result.errors.append(
                f"$ST unexpected codes initial={st.initial_code} final={st.final_code}"
            )
            return result
        status_payload = find_status_payload(st.data_records)
        if status_payload is None:
            result.errors.append(
                f"$ST missing status data record starting with 55; got {st.data_records!r}"
            )
            return result
        try:
            info = parse_status_payload(status_payload)
        except ValueError as exc:
            result.errors.append(str(exc))
            return result
        result.status_model = info.model
        result.status_revision = info.revision
        result.status_raw = info.raw_payload

        # 2. Source OFF command
        es_set = engine.transact("$ES 1")
        result.transactions.append(_txn_summary(es_set))
        if _hard_fail_code(es_set.final_code) or _hard_fail_code(es_set.initial_code):
            result.errors.append(
                f"$ES 1 failed with code initial={es_set.initial_code} final={es_set.final_code}"
            )
            return result

        # 3. Source OFF readback
        es_get = engine.transact("$ES")
        result.transactions.append(_txn_summary(es_get))
        if _hard_fail_code(es_get.final_code) or _hard_fail_code(es_get.initial_code):
            result.errors.append(
                f"$ES readback failed with code initial={es_get.initial_code} final={es_get.final_code}"
            )
            return result
        position = parse_es_position(es_get)
        result.es_position = position
        if position != 1:
            result.errors.append(
                f"$ES readback expected position 1 (OFF), got {position!r}"
            )
            return result

        # 4. NVM status
        me = engine.transact("$ME")
        result.transactions.append(_txn_summary(me))
        code = me_status_code(me)
        result.me_code = code
        if code == "0106":
            result.errors.append("fatal NVM error 0106")
            return result
        if code == "0108":
            result.warnings.append(
                "NVM recovered from backup (0108); investigate before trusting calibration"
            )
        elif code != "0000":
            result.errors.append(f"$ME unexpected code {code!r}")
            return result

        # 5. Accessories
        af = engine.transact("$AF")
        result.transactions.append(_txn_summary(af))
        if _hard_fail_code(af.final_code) or _hard_fail_code(af.initial_code):
            result.errors.append(
                f"$AF failed with code initial={af.initial_code} final={af.final_code}"
            )
            return result
        if af.data_records:
            result.af_bits = af.data_records[0].strip()
        else:
            result.warnings.append("$AF returned no accessory data record")

        # 6. Optional read-only settings
        if include_optional_readbacks:
            for cmd in OPTIONAL_READBACKS:
                try:
                    txn = engine.transact(cmd)
                    result.transactions.append(_txn_summary(txn))
                    result.optional_readbacks[cmd] = {
                        "final_code": txn.final_code,
                        "data": txn.data_records,
                    }
                    if txn.final_code in ("0022", "0110"):
                        result.warnings.append(f"{cmd} returned {txn.final_code}")
                except (ProtocolError, TimeoutError) as exc:
                    result.warnings.append(f"{cmd} skipped/failed: {exc}")

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result

    result.passed = len(result.errors) == 0
    return result
