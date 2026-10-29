"""Stage-2 / Gate C: bounded motion and single-point data transport (source OFF)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import parse_es_position
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine

_HARD_FAIL = frozenset({"0022", "0110", "0111", "0106", "0112", "0099"})


def _hard(code: Optional[str]) -> bool:
    return code in _HARD_FAIL


def _txn_summary(txn) -> dict[str, Any]:
    return {
        "command": txn.command,
        "initial_code": txn.initial_code,
        "final_code": txn.final_code,
        "data": txn.data_records,
        "raw_records": [r.raw.hex() for r in txn.records],
    }


def _parse_wavelengths(data: str) -> Optional[tuple[float, float]]:
    parts = [p.strip() for p in data.split(",")]
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def _parse_float_field(data: str) -> Optional[float]:
    text = data.strip()
    try:
        return float(text.split(",")[0].strip())
    except ValueError:
        return None


def _near(a: float, b: float, tol: float = 0.15) -> bool:
    return abs(a - b) <= tol


@dataclass
class Stage2Result:
    passed: bool
    stage1_pass: bool
    es_position: Optional[int] = None
    baseline_gm: Optional[str] = None
    baseline_sx: Optional[str] = None
    baseline_sm: Optional[str] = None
    gm_target: Optional[str] = None
    gm_readback: Optional[str] = None
    sx_readback: Optional[str] = None
    sm_readback: Optional[str] = None
    rd_data: Optional[str] = None
    restored: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_stage2(
    engine: TransactionEngine,
    *,
    stage1_pass: bool,
    gm_ex: float = 350.0,
    gm_em: float = 450.0,
    slit_nm: float = 5.0,
    rd_time_s: float = 1.0,
    motion_timeout_s: float = 60.0,
) -> Stage2Result:
    """
    Gate C sequence (source must stay OFF):
      confirm $ES → baseline readbacks → $GM move → slit moves → $DT 0 → $RD
      → restore baseline wavelengths/slits.
    """
    result = Stage2Result(passed=False, stage1_pass=stage1_pass)
    if not stage1_pass:
        result.errors.append("Stage 1 not signed off; refusing Gate C motion")
        return result

    try:
        # 0. Source OFF confirm
        es = engine.transact("$ES")
        result.transactions.append(_txn_summary(es))
        pos = parse_es_position(es)
        result.es_position = pos
        if pos != 1:
            # Try to force OFF once, then re-read.
            es_set = engine.transact("$ES 1")
            result.transactions.append(_txn_summary(es_set))
            es = engine.transact("$ES")
            result.transactions.append(_txn_summary(es))
            pos = parse_es_position(es)
            result.es_position = pos
        if pos != 1:
            result.errors.append(f"source not OFF (ES={pos!r}); aborting motion")
            return result

        # 1. Baseline
        gm0 = engine.transact("$GM")
        result.transactions.append(_txn_summary(gm0))
        sx0 = engine.transact("$SX")
        result.transactions.append(_txn_summary(sx0))
        sm0 = engine.transact("$SM")
        result.transactions.append(_txn_summary(sm0))
        if gm0.data_records:
            result.baseline_gm = gm0.data_records[0].strip()
        if sx0.data_records:
            result.baseline_sx = sx0.data_records[0].strip()
        if sm0.data_records:
            result.baseline_sm = sm0.data_records[0].strip()

        # 2. Bounded GOTO (instrument blocks until done, then one 0000)
        result.gm_target = f"{gm_ex:.1f},{gm_em:.1f}"
        gm_set = engine.transact(
            f"$GM {gm_ex:.1f},{gm_em:.1f}",
            timeout_s=motion_timeout_s,
        )
        result.transactions.append(_txn_summary(gm_set))
        if _hard(gm_set.final_code) or _hard(gm_set.initial_code):
            result.errors.append(
                f"$GM move failed initial={gm_set.initial_code} final={gm_set.final_code}"
            )
            return result
        gm_rb = engine.transact("$GM")
        result.transactions.append(_txn_summary(gm_rb))
        if not gm_rb.data_records:
            result.errors.append("$GM readback missing data")
            return result
        result.gm_readback = gm_rb.data_records[0].strip()
        wl = _parse_wavelengths(result.gm_readback)
        if wl is None or not (_near(wl[0], gm_ex) and _near(wl[1], gm_em)):
            result.errors.append(
                f"$GM readback expected ~{result.gm_target}, got {result.gm_readback!r}"
            )
            return result

        # 3. Slits one at a time (blocking 0000 when settled)
        for cmd, attr in ((f"$SX {slit_nm:.1f}", "sx_readback"), (f"$SM {slit_nm:.1f}", "sm_readback")):
            set_txn = engine.transact(cmd, timeout_s=motion_timeout_s)
            result.transactions.append(_txn_summary(set_txn))
            if _hard(set_txn.final_code) or _hard(set_txn.initial_code):
                result.errors.append(
                    f"{cmd} failed initial={set_txn.initial_code} final={set_txn.final_code}"
                )
                return result
            mnemonic = cmd.split()[0]
            rb = engine.transact(mnemonic)
            result.transactions.append(_txn_summary(rb))
            if not rb.data_records:
                result.errors.append(f"{mnemonic} readback missing data")
                return result
            value = rb.data_records[0].strip()
            setattr(result, attr, value)
            parsed = _parse_float_field(value)
            if parsed is None or not _near(parsed, slit_nm):
                result.errors.append(
                    f"{mnemonic} readback expected ~{slit_nm}, got {value!r}"
                )
                return result

        # 4. ASCII mode + single-point read (transport only; source OFF)
        dt = engine.transact("$DT 0")
        result.transactions.append(_txn_summary(dt))
        rd = engine.transact(
            f"$RD {rd_time_s:g}", idle_complete=False, timeout_s=max(motion_timeout_s, rd_time_s + 15)
        )
        result.transactions.append(_txn_summary(rd))
        if rd.final_code == "0107":
            result.warnings.append("PMT over-range 0107 during $RD (source OFF transport test)")
        if _hard(rd.final_code) and rd.final_code != "0107":
            result.errors.append(
                f"$RD failed initial={rd.initial_code} final={rd.final_code}"
            )
            return result
        if not rd.data_records:
            result.errors.append("$RD missing data record")
            return result
        result.rd_data = rd.data_records[0].strip()
        # Expect at least three commas-worth of fields: ex,em,temp,intensity
        if len(re.findall(r",", result.rd_data)) < 3:
            result.warnings.append(f"$RD data field count unexpected: {result.rd_data!r}")

        # 5. Restore baseline
        if result.baseline_gm:
            restore_gm = engine.transact(
                f"$GM {result.baseline_gm}",
                timeout_s=motion_timeout_s,
            )
            result.transactions.append(_txn_summary(restore_gm))
            if _hard(restore_gm.final_code):
                result.warnings.append(f"restore $GM failed final={restore_gm.final_code}")
        if result.baseline_sx:
            v = _parse_float_field(result.baseline_sx)
            if v is not None:
                restore_sx = engine.transact(f"$SX {v:.1f}", timeout_s=motion_timeout_s)
                result.transactions.append(_txn_summary(restore_sx))
        if result.baseline_sm:
            v = _parse_float_field(result.baseline_sm)
            if v is not None:
                restore_sm = engine.transact(f"$SM {v:.1f}", timeout_s=motion_timeout_s)
                result.transactions.append(_txn_summary(restore_sm))
        result.restored = True

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result

    result.passed = len(result.errors) == 0
    return result
