"""Stage-3 free-path empty-compartment emission scan (dark + source ON)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ls55.protocol import parse_es_position
from ls55.scan import ScanStatus, find_scan_status, parse_scan_points, wavelengths
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


def _parse_float_field(data: str) -> Optional[float]:
    try:
        return float(data.strip().split(",")[0].strip())
    except ValueError:
        return None


@dataclass
class SpectrumSeries:
    label: str
    wavelength_nm: list[float]
    intensity: list[int]
    status: Optional[dict[str, Any]] = None
    final_code: Optional[str] = None
    max_abs_intensity: int = 0


@dataclass
class FreepathResult:
    passed: bool
    stage2_pass: bool
    compartment_closed: bool
    es_before: Optional[int] = None
    es_after: Optional[int] = None
    dark: Optional[SpectrumSeries] = None
    empty_on: Optional[SpectrumSeries] = None
    restored: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _series_from_txn(
    label: str,
    txn,
    *,
    start_nm: float,
    interval_nm: float,
) -> SpectrumSeries:
    status = find_scan_status(txn.data_records)
    points = parse_scan_points(txn.data_records)
    start = start_nm
    interval = interval_nm
    if status is not None:
        # Emission-only (+speed): abscissa starts at emission monochromator.
        if status.em_nm is not None:
            start = status.em_nm
        if status.data_interval is not None:
            interval = status.data_interval
        if status.max_points is not None and len(points) > status.max_points:
            points = points[: status.max_points]
    wl = wavelengths(start, interval, len(points))
    status_dict = asdict(status) if status is not None else None
    max_abs = max((abs(p) for p in points), default=0)
    return SpectrumSeries(
        label=label,
        wavelength_nm=wl,
        intensity=points,
        status=status_dict,
        final_code=txn.final_code,
        max_abs_intensity=max_abs,
    )


def run_freepath(
    engine: TransactionEngine,
    *,
    stage2_pass: bool,
    compartment_closed: bool,
    ex_nm: float = 350.0,
    em_lo: float = 400.0,
    em_hi: float = 550.0,
    interval_nm: float = 2.0,
    speed: int = 120,
    slit_nm: float = 5.0,
    motion_timeout_s: float = 60.0,
    scan_timeout_s: float = 180.0,
) -> FreepathResult:
    """
    Empty-compartment emission scan: dark (ES=1) then empty path (ES=0).

    Always attempts to leave the source OFF and restore baseline GM/slits.
    """
    result = FreepathResult(
        passed=False,
        stage2_pass=stage2_pass,
        compartment_closed=compartment_closed,
        settings={
            "ex_nm": ex_nm,
            "em_lo": em_lo,
            "em_hi": em_hi,
            "interval_nm": interval_nm,
            "speed": speed,
            "slit_nm": slit_nm,
            "mx": 1,
        },
    )
    if not stage2_pass:
        result.errors.append("Stage 2 not signed off; refusing free-path scan")
        return result
    if not compartment_closed:
        result.errors.append(
            "compartment not confirmed closed; refusing free-path scan"
        )
        return result
    if em_hi <= em_lo:
        result.errors.append(f"em_hi ({em_hi}) must be > em_lo ({em_lo})")
        return result

    baseline_gm: Optional[str] = None
    baseline_sx: Optional[str] = None
    baseline_sm: Optional[str] = None

    try:
        # 0. Clear any leftover scan/time-drive, then confirm source OFF.
        # $AB → 0002 if idle; 0099/other if something was aborted.
        try:
            ab = engine.transact("$AB")
            result.transactions.append(_txn_summary(ab))
            if ab.final_code not in (None, "0000", "0002", "0099", "0110"):
                result.warnings.append(f"$AB final={ab.final_code}")
        except (TimeoutError, ProtocolError) as exc:
            result.warnings.append(f"$AB clear: {exc}")

        es = engine.transact("$ES")
        result.transactions.append(_txn_summary(es))
        pos = parse_es_position(es)
        result.es_before = pos
        if pos != 1:
            es_set = engine.transact("$ES 1")
            result.transactions.append(_txn_summary(es_set))
            es = engine.transact("$ES")
            result.transactions.append(_txn_summary(es))
            pos = parse_es_position(es)
            result.es_before = pos
        if pos != 1:
            result.errors.append(f"source not OFF before setup (ES={pos!r})")
            return result

        # 1. Baseline
        gm0 = engine.transact("$GM")
        result.transactions.append(_txn_summary(gm0))
        sx0 = engine.transact("$SX")
        result.transactions.append(_txn_summary(sx0))
        sm0 = engine.transact("$SM")
        result.transactions.append(_txn_summary(sm0))
        if gm0.data_records:
            baseline_gm = gm0.data_records[0].strip()
        if sx0.data_records:
            baseline_sx = sx0.data_records[0].strip()
        if sm0.data_records:
            baseline_sm = sm0.data_records[0].strip()

        # 2. Scan geometry
        for cmd in (
            "$DT 0",
            "$MX 1",
            f"$AL {em_lo:.1f}",
            f"$AH {em_hi:.1f}",
            f"$SI {interval_nm:.1f}",
            f"$SS {int(speed)}",
        ):
            txn = engine.transact(cmd)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.final_code) or _hard(txn.initial_code):
                result.errors.append(
                    f"{cmd} failed initial={txn.initial_code} final={txn.final_code}"
                )
                return result

        gm_set = engine.transact(
            f"$GM {ex_nm:.1f},{em_lo:.1f}", timeout_s=motion_timeout_s
        )
        result.transactions.append(_txn_summary(gm_set))
        if _hard(gm_set.final_code) or _hard(gm_set.initial_code):
            result.errors.append(
                f"$GM setup failed initial={gm_set.initial_code} final={gm_set.final_code}"
            )
            return result

        for cmd in (f"$SX {slit_nm:.1f}", f"$SM {slit_nm:.1f}"):
            txn = engine.transact(cmd, timeout_s=motion_timeout_s)
            result.transactions.append(_txn_summary(txn))
            if _hard(txn.final_code) or _hard(txn.initial_code):
                result.errors.append(
                    f"{cmd} failed initial={txn.initial_code} final={txn.final_code}"
                )
                return result

        # 3. Dark arm (source OFF)
        result.dark = _run_scan_arm(
            engine,
            result,
            label="dark",
            es_position=1,
            start_nm=em_lo,
            interval_nm=interval_nm,
            scan_timeout_s=scan_timeout_s,
        )
        if result.dark is None or not result.dark.intensity:
            result.errors.append("dark scan produced no points")
        else:
            # 4. Empty-ON arm (skip if dark failed — still clean up below)
            result.empty_on = _run_scan_arm(
                engine,
                result,
                label="empty_on",
                es_position=0,
                start_nm=em_lo,
                interval_nm=interval_nm,
                scan_timeout_s=scan_timeout_s,
            )
            if result.empty_on is None or not result.empty_on.intensity:
                result.errors.append("empty-ON scan produced no points")

        if result.empty_on and result.empty_on.max_abs_intensity >= 900000:
            result.warnings.append(
                f"empty-ON max |intensity|={result.empty_on.max_abs_intensity} "
                "(possible scatter/overload; not an automatic FAIL)"
            )
        if result.empty_on and result.empty_on.final_code == "0107":
            result.warnings.append("PMT over-range 0107 on empty-ON scan")
        if result.dark and result.dark.final_code == "0107":
            result.warnings.append("PMT over-range 0107 on dark scan")

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")

    # 5. Always OFF + restore
    try:
        off = engine.transact("$ES 1")
        result.transactions.append(_txn_summary(off))
        es_end = None
        for attempt in range(2):
            try:
                es_end = engine.transact("$ES")
                result.transactions.append(_txn_summary(es_end))
                break
            except (TimeoutError, ProtocolError) as exc:
                if attempt == 0:
                    result.warnings.append(f"ES readback retry after: {exc}")
                    continue
                result.errors.append(f"ES readback after OFF failed: {exc}")
        if es_end is not None:
            result.es_after = parse_es_position(es_end)
        elif off.final_code == "0000":
            result.warnings.append(
                "$ES 1 accepted but readback failed; treat source as likely OFF"
            )
            result.es_after = 1
        if result.es_after != 1:
            result.errors.append(
                f"source not OFF after scan (ES={result.es_after!r}); "
                "do not open compartment"
            )

        if baseline_gm:
            restore_gm = engine.transact(
                f"$GM {baseline_gm}", timeout_s=motion_timeout_s
            )
            result.transactions.append(_txn_summary(restore_gm))
        if baseline_sx:
            v = _parse_float_field(baseline_sx)
            if v is not None:
                restore_sx = engine.transact(
                    f"$SX {v:.1f}", timeout_s=motion_timeout_s
                )
                result.transactions.append(_txn_summary(restore_sx))
        if baseline_sm:
            v = _parse_float_field(baseline_sm)
            if v is not None:
                restore_sm = engine.transact(
                    f"$SM {v:.1f}", timeout_s=motion_timeout_s
                )
                result.transactions.append(_txn_summary(restore_sm))
        result.restored = True
    except (TimeoutError, ProtocolError) as exc:
        result.errors.append(f"cleanup: {exc}")

    result.passed = (
        len(result.errors) == 0
        and result.dark is not None
        and bool(result.dark.intensity)
        and result.empty_on is not None
        and bool(result.empty_on.intensity)
        and result.es_after == 1
    )
    return result


def _run_scan_arm(
    engine: TransactionEngine,
    result: FreepathResult,
    *,
    label: str,
    es_position: int,
    start_nm: float,
    interval_nm: float,
    scan_timeout_s: float,
) -> Optional[SpectrumSeries]:
    es_set = engine.transact(f"$ES {es_position}")
    result.transactions.append(_txn_summary(es_set))
    es_rb = engine.transact("$ES")
    result.transactions.append(_txn_summary(es_rb))
    pos = parse_es_position(es_rb)
    if pos != es_position:
        result.errors.append(
            f"{label}: $ES {es_position} readback got {pos!r}"
        )
        return None

    sc = engine.transact(
        "$SC 1",
        idle_complete=False,
        timeout_s=scan_timeout_s,
    )
    result.transactions.append(_txn_summary(sc))
    if _hard(sc.initial_code):
        result.errors.append(
            f"{label}: $SC rejected initial={sc.initial_code}"
        )
        return None
    if _hard(sc.final_code) and sc.final_code != "0107":
        result.errors.append(
            f"{label}: $SC failed final={sc.final_code}"
        )
        return None
    if find_scan_status(sc.data_records) is None:
        result.warnings.append(f"{label}: scan status header not parsed")

    return _series_from_txn(
        label, sc, start_nm=start_nm, interval_nm=interval_nm
    )
