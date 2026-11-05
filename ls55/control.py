"""WinLab Status/Setup and Single Read helpers (setpoint vs verified readback)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import (
    decode_accessories,
    find_status_payload,
    me_status_code,
    parse_es_position,
    parse_status_payload,
)
from ls55.source import SOURCE_OFF, SOURCE_ON, ensure_source_off
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine

_HARD_FAIL = frozenset({"0022", "0110", "0112", "0106"})
_CLIP_SOFT = 900_000

# Parameter bounds (instrument-specs.md §3).
EX_NM_MIN, EX_NM_MAX = 200.0, 800.0
EM_NM_MIN, EM_NM_MAX = 200.0, 900.0
SX_MIN, SX_MAX = 2.5, 15.0
SM_MIN, SM_MAX = 0.0, 20.0
FW_MIN, FW_MAX = 1, 8
PH_ALLOWED = frozenset({0, 1, 2})
PV_MIN, PV_MAX = 0, 999


def _txn_summary(txn) -> dict[str, Any]:
    return {
        "command": txn.command,
        "initial_code": txn.initial_code,
        "final_code": txn.final_code,
        "data": txn.data_records,
        "raw_records": [r.raw.hex() for r in txn.records],
    }


def _hard(code: Optional[str]) -> bool:
    return code in _HARD_FAIL


def _near(a: float, b: float, tol: float = 0.15) -> bool:
    return abs(a - b) <= tol


def _parse_wavelengths(data: str) -> Optional[tuple[float, float]]:
    parts = [p.strip() for p in data.split(",")]
    if len(parts) < 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def sanitize_wavelength_token(token: str) -> Optional[float]:
    """Parse a wavelength field, tolerating a single Class-B glitch byte."""
    cleaned = token.strip().replace("\ufffd", "0")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_float_field(data: str) -> Optional[float]:
    return sanitize_wavelength_token(data.split(",")[0])


def _parse_rd_intensity(data: str) -> Optional[float]:
    """
    Parse ``$RD`` ASCII payload.

    Observed shape: ``ex,em,******|temp,intensity`` (temp may be stars).
    """
    parts = [p.strip() for p in data.split(",")]
    if not parts:
        return None
    # Intensity is the last numeric field.
    for token in reversed(parts):
        cleaned = token.replace("*", "").strip()
        if not cleaned:
            continue
        try:
            return float(cleaned)
        except ValueError:
            continue
    return None


@dataclass
class OpticalSetup:
    """WinLab Setup targets (commanded setpoints)."""

    ex_nm: Optional[float] = None
    em_nm: Optional[float] = None
    ex_slit: Optional[float] = None
    em_slit: Optional[float] = None
    fw: Optional[int] = None
    ph: Optional[int] = None
    cx: Optional[int] = None
    pv: Optional[int] = None  # -1 = auto

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.ex_nm is not None and self.ex_nm != 0.0:
            if not (EX_NM_MIN <= self.ex_nm <= EX_NM_MAX):
                errors.append(f"ex_nm {self.ex_nm} outside {EX_NM_MIN}–{EX_NM_MAX}")
        if self.em_nm is not None and self.em_nm != 0.0:
            if not (EM_NM_MIN <= self.em_nm <= EM_NM_MAX):
                errors.append(f"em_nm {self.em_nm} outside {EM_NM_MIN}–{EM_NM_MAX}")
        if self.ex_slit is not None and not (SX_MIN <= self.ex_slit <= SX_MAX):
            errors.append(f"ex_slit {self.ex_slit} outside {SX_MIN}–{SX_MAX}")
        if self.em_slit is not None and not (SM_MIN <= self.em_slit <= SM_MAX):
            errors.append(f"em_slit {self.em_slit} outside {SM_MIN}–{SM_MAX}")
        if self.fw is not None and not (FW_MIN <= self.fw <= FW_MAX):
            errors.append(f"fw {self.fw} outside {FW_MIN}–{FW_MAX}")
        if self.ph is not None and self.ph not in PH_ALLOWED:
            errors.append(f"ph {self.ph} not in {sorted(PH_ALLOWED)}")
        if self.cx is not None and self.cx not in (0, 1):
            errors.append(f"cx {self.cx} must be 0 or 1")
        if self.pv is not None and self.pv != -1 and not (PV_MIN <= self.pv <= PV_MAX):
            errors.append(f"pv {self.pv} outside {PV_MIN}–{PV_MAX} or -1")
        return errors


@dataclass
class InstrumentStatusSnapshot:
    """WinLab Status: verified hardware readbacks + accessory / NVM health."""

    ok: bool
    es_position: Optional[int] = None
    me_code: Optional[str] = None
    status: Optional[dict[str, Any]] = None
    status_raw: Optional[str] = None
    accessories: Optional[dict[str, Any]] = None
    af_bits: Optional[str] = None
    readbacks: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApplySetupResult:
    ok: bool
    setup: dict[str, Any] = field(default_factory=dict)
    readbacks: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SingleReadResult:
    ok: bool
    ex_nm: float
    em_nm: float
    integration_s: float
    intensity: Optional[float] = None
    dark_intensity: Optional[float] = None
    corrected: Optional[float] = None
    clipped: bool = False
    es_after: Optional[int] = None
    rd_raw: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_status_snapshot(engine: TransactionEngine) -> InstrumentStatusSnapshot:
    """Read Status/Setup registers without moving optics (shutter left as-is)."""
    result = InstrumentStatusSnapshot(ok=False)
    try:
        es = engine.transact("$ES")
        result.transactions.append(_txn_summary(es))
        result.es_position = parse_es_position(es)

        st = engine.transact("$ST")
        result.transactions.append(_txn_summary(st))
        if _hard(st.initial_code) or _hard(st.final_code):
            result.errors.append(
                f"$ST hard-fail initial={st.initial_code} final={st.final_code}"
            )
            return result
        payload = find_status_payload(st.data_records)
        if payload is None:
            result.errors.append(f"$ST missing status payload; got {st.data_records!r}")
            return result
        result.status_raw = payload
        info = parse_status_payload(payload)
        result.status = {
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
        }

        me = engine.transact("$ME")
        result.transactions.append(_txn_summary(me))
        result.me_code = me_status_code(me)
        if result.me_code == "0106":
            result.errors.append("$ME = 0106 fatal NVM")
            return result
        if result.me_code == "0108":
            result.warnings.append("$ME = 0108 NVM recovered from backup")

        af = engine.transact("$AF")
        result.transactions.append(_txn_summary(af))
        if af.data_records:
            result.af_bits = af.data_records[0]
            decoded = decode_accessories(result.af_bits)
            result.accessories = {
                "raw": decoded.raw,
                "flags": decoded.flags,
                "fitted": [n for n, on in decoded.flags.items() if on],
                "extra_bits": decoded.extra_bits,
            }

        for cmd in ("$SN", "$HZ", "$PV", "$CX", "$FW", "$PH", "$PT", "$GM", "$SX", "$SM"):
            try:
                txn = engine.transact(cmd)
            except (TimeoutError, ProtocolError) as exc:
                result.warnings.append(f"{cmd} failed: {exc}")
                result.readbacks[cmd] = {"error": str(exc)}
                continue
            result.transactions.append(_txn_summary(txn))
            result.readbacks[cmd] = {
                "initial_code": txn.initial_code,
                "final_code": txn.final_code,
                "data": txn.data_records,
            }
            if cmd == "$PT" and txn.final_code == "0107":
                result.warnings.append("$PT latched PMT over-range (0107)")

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result
    except ValueError as exc:
        result.errors.append(str(exc))
        return result

    result.ok = not result.errors
    return result


def apply_optical_setup(
    engine: TransactionEngine,
    setup: OpticalSetup,
    *,
    motion_timeout_s: float = 60.0,
    require_source_off: bool = True,
) -> ApplySetupResult:
    """Apply WinLab Setup setpoints and verify readbacks (prefer shutter OFF)."""
    result = ApplySetupResult(ok=False, setup=asdict(setup))
    errors = setup.validate()
    if errors:
        result.errors.extend(errors)
        return result

    try:
        if require_source_off:
            off = ensure_source_off(engine)
            result.transactions.extend(off.transactions)
            if not off.ok:
                result.errors.extend(off.errors or ["failed to force $ES 1 before setup"])
                return result

        if setup.ex_nm is not None and setup.em_nm is not None:
            cmd = f"$GM {setup.ex_nm:.1f},{setup.em_nm:.1f}"
            txn = engine.transact(cmd, idle_complete=False, timeout_s=motion_timeout_s)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(
                    f"{cmd} failed initial={txn.initial_code} final={txn.final_code}"
                )
                return result
            rb = engine.transact("$GM")
            result.transactions.append(_txn_summary(rb))
            if not rb.data_records:
                result.errors.append("$GM readback missing data")
                return result
            raw = rb.data_records[0].strip()
            wl = _parse_wavelengths(raw)
            if wl is None:
                # Class-B tolerant parse of each field.
                parts = raw.split(",")
                if len(parts) >= 2:
                    a = sanitize_wavelength_token(parts[0])
                    b = sanitize_wavelength_token(parts[1])
                    wl = (a, b) if a is not None and b is not None else None
            result.readbacks["$GM"] = raw
            if wl is None or not (
                _near(wl[0], setup.ex_nm) and _near(wl[1], setup.em_nm)
            ):
                result.errors.append(
                    f"$GM readback expected ~{setup.ex_nm},{setup.em_nm}; got {raw!r}"
                )
                return result

        if setup.ex_slit is not None:
            cmd = f"$SX {setup.ex_slit:.1f}"
            txn = engine.transact(cmd, idle_complete=False, timeout_s=motion_timeout_s)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(f"{cmd} failed final={txn.final_code}")
                return result
            rb = engine.transact("$SX")
            result.transactions.append(_txn_summary(rb))
            raw = rb.data_records[0].strip() if rb.data_records else ""
            result.readbacks["$SX"] = raw
            parsed = _parse_float_field(raw)
            if parsed is None or not _near(parsed, setup.ex_slit):
                result.errors.append(f"$SX readback expected ~{setup.ex_slit}; got {raw!r}")
                return result

        if setup.em_slit is not None:
            cmd = f"$SM {setup.em_slit:.1f}"
            txn = engine.transact(cmd, idle_complete=False, timeout_s=motion_timeout_s)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(f"{cmd} failed final={txn.final_code}")
                return result
            rb = engine.transact("$SM")
            result.transactions.append(_txn_summary(rb))
            raw = rb.data_records[0].strip() if rb.data_records else ""
            result.readbacks["$SM"] = raw
            parsed = _parse_float_field(raw)
            if parsed is None or not _near(parsed, setup.em_slit):
                result.errors.append(f"$SM readback expected ~{setup.em_slit}; got {raw!r}")
                return result

        if setup.fw is not None:
            cmd = f"$FW {int(setup.fw)}"
            txn = engine.transact(cmd)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(f"{cmd} failed final={txn.final_code}")
                return result
            rb = engine.transact("$FW")
            result.transactions.append(_txn_summary(rb))
            result.readbacks["$FW"] = rb.data_records[0].strip() if rb.data_records else None

        if setup.ph is not None:
            cmd = f"$PH {int(setup.ph)}"
            txn = engine.transact(cmd)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(f"{cmd} failed final={txn.final_code}")
                return result

        if setup.cx is not None:
            cmd = f"$CX {int(setup.cx)}"
            txn = engine.transact(cmd)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(f"{cmd} failed final={txn.final_code}")
                return result

        if setup.pv is not None:
            cmd = f"$PV {int(setup.pv)}"
            txn = engine.transact(cmd)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.initial_code) or _hard(txn.final_code):
                result.errors.append(f"{cmd} failed final={txn.final_code}")
                return result

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
        return result
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
        return result

    result.ok = not result.errors
    return result


def run_single_read(
    engine: TransactionEngine,
    *,
    ex_nm: float,
    em_nm: float,
    integration_s: float = 1.0,
    dark_correct: bool = True,
    motion_timeout_s: float = 60.0,
) -> SingleReadResult:
    """
    WinLab Single Read (Ch. 7): move to Ex/Em, optional dark, ``$RD``, restore Xe OFF.
    """
    result = SingleReadResult(
        ok=False,
        ex_nm=ex_nm,
        em_nm=em_nm,
        integration_s=integration_s,
    )
    setup = OpticalSetup(ex_nm=ex_nm, em_nm=em_nm)
    try:
        applied = apply_optical_setup(
            engine, setup, motion_timeout_s=motion_timeout_s, require_source_off=True
        )
        result.transactions.extend(applied.transactions)
        if not applied.ok:
            result.errors.extend(applied.errors)
            return result

        dt = engine.transact("$DT 0")
        result.transactions.append(_txn_summary(dt))

        if dark_correct:
            # Dark with shutter OFF (already OFF).
            rd_dark = engine.transact(
                f"$RD {integration_s:g}",
                idle_complete=False,
                timeout_s=max(motion_timeout_s, integration_s + 15.0),
            )
            result.transactions.append(_txn_summary(rd_dark))
            if rd_dark.data_records:
                result.dark_intensity = _parse_rd_intensity(rd_dark.data_records[0])

        # Open shutter, read, close in finally.
        es_on = engine.transact(f"$ES {SOURCE_ON}")
        result.transactions.append(_txn_summary(es_on))
        es_rb = engine.transact("$ES")
        result.transactions.append(_txn_summary(es_rb))
        if parse_es_position(es_rb) != SOURCE_ON:
            result.errors.append("$ES failed to open for Single Read")
            return result

        rd = engine.transact(
            f"$RD {integration_s:g}",
            idle_complete=False,
            timeout_s=max(motion_timeout_s, integration_s + 15.0),
        )
        result.transactions.append(_txn_summary(rd))
        if rd.final_code == "0107":
            result.warnings.append("PMT over-range 0107 during $RD")
            result.clipped = True
        if _hard(rd.final_code) and rd.final_code != "0107":
            result.errors.append(f"$RD failed final={rd.final_code}")
        elif rd.data_records:
            result.rd_raw = rd.data_records[0].strip()
            result.intensity = _parse_rd_intensity(result.rd_raw)
            if result.intensity is not None and abs(result.intensity) >= _CLIP_SOFT:
                result.clipped = True
                result.warnings.append(
                    f"intensity near clip ceiling (|I|={result.intensity:.0f})"
                )
            if (
                dark_correct
                and result.intensity is not None
                and result.dark_intensity is not None
            ):
                result.corrected = result.intensity - result.dark_intensity
            else:
                result.corrected = result.intensity

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
    finally:
        try:
            off = ensure_source_off(engine)
            result.transactions.extend(off.transactions)
            result.es_after = off.es_after
            if not off.ok:
                result.errors.extend(off.errors or ["failed to restore $ES 1"])
        except (TimeoutError, ProtocolError) as exc:
            result.errors.append(f"cleanup: {exc}")

    result.ok = (
        not result.errors
        and result.intensity is not None
        and result.es_after == SOURCE_OFF
    )
    return result
