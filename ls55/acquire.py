"""WinLab Scan: staged emission/excitation spectrum acquisition with live points."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ls55.protocol import Record, Transaction, parse_es_position
from ls55.scan import find_scan_status, parse_scan_points, wavelengths
from ls55.sidecar import (
    OpticalPathConfig,
    SampleMetadata,
    build_run_sidecar,
)
from ls55.source import SOURCE_OFF, SOURCE_ON, ensure_source_off
from ls55.transactions import ProtocolError, TimeoutError, TransactionEngine

_HARD_FAIL = frozenset({"0022", "0110", "0111", "0106", "0112"})
_CLIP_SOFT = 900_000

OnPointCallback = Callable[[float, int, str], None]  # wl, intensity, arm_label
OnPhaseCallback = Callable[[str, dict[str, Any]], None]


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


def _parse_float_field(data: str) -> Optional[float]:
    try:
        return float(data.strip().split(",")[0].strip())
    except ValueError:
        return None


@dataclass
class ScanConfig:
    """
    WinLab Scan method parameters.

    ``mx=1`` (Em): fixed Ex at ``ex_nm``; Em scans ``em_lo``→``em_hi``.
    ``mx=2`` (Ex): fixed Em at ``ex_nm`` (parking wavelength); Ex scans ``em_lo``→``em_hi``.
    Synchronous (``mx=3``) is deferred to Stage 3.
    """

    mx: int = 1  # 1=Em, 2=Ex (sync deferred to Stage 3)
    ex_nm: float = 350.0
    em_lo: float = 400.0
    em_hi: float = 550.0
    interval_nm: float = 2.0
    speed: int = 120
    ex_slit: float = 5.0
    em_slit: float = 5.0
    include_dark: bool = True
    n_accumulate: int = 1

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.mx not in (1, 2):
            errors.append(f"mx {self.mx} not supported yet (use 1=Em or 2=Ex; sync=Stage 3)")
        if self.em_hi <= self.em_lo:
            errors.append(f"scan hi ({self.em_hi}) must be > scan lo ({self.em_lo})")
        if self.interval_nm <= 0:
            errors.append("interval_nm must be > 0")
        if self.n_accumulate < 1:
            errors.append("n_accumulate must be >= 1")
        if not (10 <= abs(int(self.speed)) <= 1500):
            errors.append("speed must be in 10–1500 nm/min")
        return errors

    def scan_lo(self) -> float:
        return self.em_lo

    def scan_hi(self) -> float:
        return self.em_hi

    def fixed_other_nm(self) -> float:
        """Fixed mono wavelength: Ex when mx=1, Em when mx=2."""
        return self.ex_nm

    def estimated_points(self) -> int:
        span = abs(self.scan_hi() - self.scan_lo())
        return int(round(span / self.interval_nm)) + 1

    def estimated_arm_duration_s(self) -> float:
        span = abs(self.scan_hi() - self.scan_lo())
        return (span / float(abs(self.speed))) * 60.0 + 15.0  # +setup margin


@dataclass
class SpectrumSeries:
    label: str
    wavelength_nm: list[float]
    intensity: list[int]
    status: Optional[dict[str, Any]] = None
    final_code: Optional[str] = None
    max_abs_intensity: int = 0
    aborted: bool = False


@dataclass
class SpectrumScanResult:
    passed: bool
    config: dict[str, Any] = field(default_factory=dict)
    dark: Optional[SpectrumSeries] = None
    sample: Optional[SpectrumSeries] = None
    accumulated_mean: Optional[list[float]] = None
    accumulated_sd: Optional[list[float]] = None
    es_after: Optional[int] = None
    restored: bool = False
    aborted: bool = False
    clipped: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _series_from_txn(
    label: str,
    txn: Transaction,
    *,
    start_nm: float,
    interval_nm: float,
    aborted: bool = False,
) -> SpectrumSeries:
    status = find_scan_status(txn.data_records)
    points = parse_scan_points(txn.data_records)
    start = start_nm
    interval = interval_nm
    if status is not None:
        if status.em_nm is not None and label != "excitation":
            start = status.em_nm
        if status.ex_nm is not None and label == "excitation":
            start = status.ex_nm
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
        aborted=aborted,
    )


def _stream_scan_points(
    txn: Transaction,
    *,
    start_nm: float,
    interval_nm: float,
    arm_label: str,
    on_point: Optional[OnPointCallback],
    seen_points: list[int],
) -> None:
    """Emit newly parsed intensity points after each data record."""
    if on_point is None:
        return
    # Re-parse full point list; emit only new indices.
    points = parse_scan_points(txn.data_records)
    status = find_scan_status(txn.data_records)
    start = start_nm
    interval = interval_nm
    if status is not None:
        if status.em_nm is not None:
            start = status.em_nm
        if status.data_interval is not None:
            interval = status.data_interval
    while len(seen_points) < len(points):
        i = len(seen_points)
        inten = points[i]
        seen_points.append(inten)
        wl = round(start + i * interval, 1)
        on_point(wl, inten, arm_label)


def run_spectrum_scan(
    engine: TransactionEngine,
    config: ScanConfig,
    *,
    compartment_closed: bool = True,
    motion_timeout_s: float = 60.0,
    scan_timeout_s: float | None = None,
    on_point: Optional[OnPointCallback] = None,
    on_phase: Optional[OnPhaseCallback] = None,
) -> SpectrumScanResult:
    """
    Staged spectrum scan: setup → optional dark → sample ON → restore Xe OFF.

    Supports live ``on_point`` callbacks and ``engine.request_abort()`` during ``$SC``.
    """
    result = SpectrumScanResult(passed=False, config=asdict(config))
    errors = config.validate()
    if errors:
        result.errors.extend(errors)
        return result
    if not compartment_closed:
        result.errors.append("compartment not confirmed closed; refusing scan")
        return result

    timeout = scan_timeout_s
    if timeout is None:
        timeout = max(180.0, config.estimated_arm_duration_s() * 2.5)

    def phase(name: str, **payload: Any) -> None:
        if on_phase is not None:
            on_phase(name, payload)

    baseline_gm: Optional[str] = None
    baseline_sx: Optional[str] = None
    baseline_sm: Optional[str] = None

    try:
        phase("clear")
        try:
            ab = engine.transact("$AB")
            result.transactions.append(_txn_summary(ab))
        except (TimeoutError, ProtocolError) as exc:
            result.warnings.append(f"$AB clear: {exc}")

        off = ensure_source_off(engine)
        result.transactions.extend(off.transactions)
        if not off.ok:
            result.errors.extend(off.errors or ["source not OFF before setup"])
        else:
            phase("baseline")
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

            phase("configure")
            scan_lo = config.scan_lo()
            scan_hi = config.scan_hi()
            fixed = config.fixed_other_nm()
            setup_ok = True
            for cmd in (
                "$DT 0",
                f"$MX {int(config.mx)}",
                f"$AL {scan_lo:.1f}",
                f"$AH {scan_hi:.1f}",
                f"$SI {config.interval_nm:.1f}",
                f"$SS {int(config.speed)}",
            ):
                txn = engine.transact(cmd)
                result.transactions.append(_txn_summary(txn))
                if _hard(txn.final_code) or _hard(txn.initial_code):
                    result.errors.append(
                        f"{cmd} failed initial={txn.initial_code} final={txn.final_code}"
                    )
                    setup_ok = False
                    break

            if setup_ok:
                if config.mx == 1:
                    gm_cmd = f"$GM {fixed:.1f},{scan_lo:.1f}"
                else:
                    # Ex scan: park Em at fixed (ex_nm), start Ex at scan_lo.
                    gm_cmd = f"$GM {scan_lo:.1f},{fixed:.1f}"
                gm_set = engine.transact(gm_cmd, timeout_s=motion_timeout_s)
                result.transactions.append(_txn_summary(gm_set))
                if _hard(gm_set.final_code) or _hard(gm_set.initial_code):
                    result.errors.append(
                        f"$GM setup failed initial={gm_set.initial_code} final={gm_set.final_code}"
                    )
                    setup_ok = False

            if setup_ok:
                for cmd in (f"$SX {config.ex_slit:.1f}", f"$SM {config.em_slit:.1f}"):
                    txn = engine.transact(cmd, timeout_s=motion_timeout_s)
                    result.transactions.append(_txn_summary(txn))
                    if _hard(txn.final_code) or _hard(txn.initial_code):
                        result.errors.append(
                            f"{cmd} failed initial={txn.initial_code} final={txn.final_code}"
                        )
                        setup_ok = False
                        break

            start_nm = scan_lo
            if setup_ok and config.include_dark:
                phase("dark")
                result.dark = _run_scan_arm(
                    engine,
                    result,
                    label="dark",
                    es_position=SOURCE_OFF,
                    start_nm=start_nm,
                    interval_nm=config.interval_nm,
                    scan_timeout_s=timeout,
                    on_point=on_point,
                )
                if result.dark is None or not result.dark.intensity:
                    result.errors.append("dark scan produced no points")
                if result.dark and result.dark.aborted:
                    result.aborted = True

            if setup_ok and not result.aborted:
                samples: list[SpectrumSeries] = []
                for i in range(config.n_accumulate):
                    phase("sample", accumulate_index=i)
                    arm = _run_scan_arm(
                        engine,
                        result,
                        label="sample" if config.n_accumulate == 1 else f"sample_{i+1}",
                        es_position=SOURCE_ON,
                        start_nm=start_nm,
                        interval_nm=config.interval_nm,
                        scan_timeout_s=timeout,
                        on_point=on_point,
                    )
                    if arm is None or not arm.intensity:
                        result.errors.append("sample scan produced no points")
                        break
                    samples.append(arm)
                    if arm.aborted:
                        result.aborted = True
                        break
                    if arm.max_abs_intensity >= _CLIP_SOFT:
                        result.clipped = True
                        result.warnings.append(
                            f"sample max |intensity|={arm.max_abs_intensity} (clip warning)"
                        )
                    if arm.final_code == "0107":
                        result.clipped = True
                        result.warnings.append("PMT over-range 0107 on sample scan")

                if samples:
                    result.sample = samples[-1] if len(samples) == 1 else samples[0]
                    if len(samples) > 1:
                        n = min(len(s.intensity) for s in samples)
                        means: list[float] = []
                        sds: list[float] = []
                        for j in range(n):
                            vals = [float(s.intensity[j]) for s in samples]
                            mean = sum(vals) / len(vals)
                            means.append(mean)
                            if len(vals) > 1:
                                var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
                                sds.append(var**0.5)
                            else:
                                sds.append(0.0)
                        result.accumulated_mean = means
                        result.accumulated_sd = sds
                        result.sample = SpectrumSeries(
                            label="sample_mean",
                            wavelength_nm=samples[0].wavelength_nm[:n],
                            intensity=[int(round(v)) for v in means],
                            status=samples[0].status,
                            final_code=samples[-1].final_code,
                            max_abs_intensity=max(abs(int(round(v))) for v in means),
                        )

    except TimeoutError as exc:
        result.errors.append(f"timeout: {exc}")
    except ProtocolError as exc:
        result.errors.append(f"protocol: {exc}")
    finally:
        # Guaranteed Xe OFF + baseline restore even after mid-setup failure.
        phase("cleanup")
        try:
            off = ensure_source_off(engine)
            result.transactions.extend(off.transactions)
            result.es_after = off.es_after
            if not off.ok:
                result.errors.extend(off.errors or ["source not OFF after scan"])

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
        and result.sample is not None
        and bool(result.sample.intensity)
        and result.es_after == SOURCE_OFF
        and not result.aborted
    )
    phase("done", passed=result.passed)
    return result


def _run_scan_arm(
    engine: TransactionEngine,
    result: SpectrumScanResult,
    *,
    label: str,
    es_position: int,
    start_nm: float,
    interval_nm: float,
    scan_timeout_s: float,
    on_point: Optional[OnPointCallback],
) -> Optional[SpectrumSeries]:
    es_set = engine.transact(f"$ES {es_position}")
    result.transactions.append(_txn_summary(es_set))
    es_rb = engine.transact("$ES")
    result.transactions.append(_txn_summary(es_rb))
    pos = parse_es_position(es_rb)
    if pos != es_position:
        result.errors.append(f"{label}: $ES {es_position} readback got {pos!r}")
        return None

    seen: list[int] = []

    def _on_record(record: Record, txn: Transaction) -> None:
        _stream_scan_points(
            txn,
            start_nm=start_nm,
            interval_nm=interval_nm,
            arm_label=label,
            on_point=on_point,
            seen_points=seen,
        )

    sc = engine.transact(
        "$SC 1",
        idle_complete=False,
        timeout_s=scan_timeout_s,
        on_record=_on_record,
        allow_abort=True,
    )
    result.transactions.append(_txn_summary(sc))
    aborted = sc.final_code == "0099"
    if aborted:
        result.warnings.append(f"{label}: scan aborted ($AB → 0099)")
    if _hard(sc.initial_code):
        result.errors.append(f"{label}: $SC rejected initial={sc.initial_code}")
        return None
    if _hard(sc.final_code) and sc.final_code not in {"0107", "0099"}:
        result.errors.append(f"{label}: $SC failed final={sc.final_code}")
        return None
    if find_scan_status(sc.data_records) is None and not aborted:
        result.warnings.append(f"{label}: scan status header not parsed")

    return _series_from_txn(
        label,
        sc,
        start_nm=start_nm,
        interval_nm=interval_nm,
        aborted=aborted,
    )


def persist_scan_run(
    result: SpectrumScanResult,
    *,
    out_dir: Path,
    experiment: str = "dashboard-scan",
    method_name: Optional[str] = None,
    series_id: Optional[str] = None,
    replicate_kind: Optional[str] = None,
    sample_id: Optional[str] = None,
    dilution: Optional[str] = None,
    geometry: str = "right_angle_4w",
    role: str = "sample",  # sample | blank
    instrument: Optional[dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
    write_png: bool = True,
) -> dict[str, Any]:
    """
    Write Stage-1 GLP artifacts for a completed scan: ``.csv`` + ``.json`` (+ optional PNG).

    Blank role writes ``empty_on`` so the CSV is discoverable as a matched blank.
    Sample role writes ``sample_on`` / ``blank``(dark) / ``corrected``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stem = f"{experiment}-{stamp}"
    csv_path = out_dir / f"{stem}.csv"
    json_path = out_dir / f"{stem}.json"
    png_path = out_dir / f"{stem}.png"

    sample = result.sample
    dark = result.dark
    if sample is None or not sample.wavelength_nm or not sample.intensity:
        raise ValueError("scan result has no sample spectrum to persist")

    wl = list(sample.wavelength_nm)
    sample_i = [float(v) for v in sample.intensity]
    if dark is not None and dark.intensity:
        dark_i = [float(v) for v in dark.intensity[: len(sample_i)]]
        while len(dark_i) < len(sample_i):
            dark_i.append(0.0)
    else:
        dark_i = [0.0] * len(sample_i)
    corrected = [s - d for s, d in zip(sample_i, dark_i)]

    lines: list[str]
    if role == "blank":
        lines = ["wavelength_nm,dark,empty_on\n"]
        for i in range(len(wl)):
            lines.append(f"{wl[i]},{dark_i[i]},{sample_i[i]}\n")
    else:
        lines = ["wavelength_nm,sample_on,blank,corrected\n"]
        for i in range(len(wl)):
            lines.append(f"{wl[i]},{sample_i[i]},{dark_i[i]},{corrected[i]}\n")
    csv_path.write_text("".join(lines), encoding="utf-8")

    optics = dict(result.config or {})
    optics.setdefault("ex_nm", optics.get("ex_nm"))
    optics.setdefault("slit_nm", optics.get("ex_slit"))
    optics.setdefault("interval_nm", optics.get("interval_nm"))
    optics.setdefault("speed", optics.get("speed"))

    artifacts: dict[str, Any] = {"csv": str(csv_path)}
    if write_png:
        try:
            from ls55.plot_spectrum import plot_freepath_comparison

            plot_freepath_comparison(
                png_path,
                wavelength_nm=wl,
                dark=dark_i,
                empty_on=sample_i,
                title=f"LS 55 {experiment}",
                subtitle=f"{role} · {replicate_kind or ''}".strip(" ·"),
            )
            artifacts["png"] = str(png_path)
        except Exception as exc:  # pragma: no cover - plotting optional offline
            artifacts["png_error"] = str(exc)

    sidecar = build_run_sidecar(
        experiment=experiment,
        method_name=method_name or experiment,
        series_id=series_id or stamp,
        replicate_kind=replicate_kind,
        passed=result.passed,
        script_name="ls55.service",
        instrument=instrument,
        optics=optics,
        optical_path=OpticalPathConfig(geometry=geometry),
        sample=SampleMetadata(sample_id=sample_id, dilution=dilution),
        artifacts=artifacts,
        repo_root=repo_root,
        warnings=list(result.warnings),
        errors=list(result.errors),
        extra={"role": role, "clipped": result.clipped, "csv": str(csv_path)},
    )
    sidecar.write_json(json_path)
    return {
        "csv": str(csv_path),
        "json": str(json_path),
        "png": artifacts.get("png"),
        "run_id": stem,
        "role": role,
    }
