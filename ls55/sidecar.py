"""GLP method + run sidecar builders (roadmap §7 schema)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def git_commit_hash(repo_root: Path | None = None) -> Optional[str]:
    """Best-effort short git HEAD hash; None if unavailable."""
    cwd = str(repo_root) if repo_root is not None else None
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
        )
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class OpticalPathConfig:
    geometry: str = "right_angle_4w"  # free_path | right_angle_4w | transmission_2w_mirror | uv_fiber_probe
    holder_id: Optional[str] = None
    cuvette_windows: Optional[int] = None
    cuvette_material: Optional[str] = None
    path_length_mm: Optional[float] = None
    fiber_id: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ExcitationSourceConfig:
    source_type: str = "internal_xe"  # internal_xe | external_laser | ns_spark_gap
    interlock_ok: Optional[bool] = None
    notes: Optional[str] = None


@dataclass
class SampleMetadata:
    sample_id: Optional[str] = None
    solvent: Optional[str] = None
    dilution: Optional[str] = None
    concentration: Optional[str] = None
    temperature_c: Optional[float] = None
    a_ex: Optional[float] = None
    a_em: Optional[float] = None


@dataclass
class ReviewAnalysis:
    blank_csv: Optional[str] = None
    guide_nm: Optional[float] = None
    half_window_nm: Optional[float] = None
    noise_lo_nm: Optional[float] = None
    noise_hi_nm: Optional[float] = None
    wing_left: Optional[tuple[float, float]] = None
    wing_right: Optional[tuple[float, float]] = None
    peak: Optional[dict[str, Any]] = None
    absolute_snr: Optional[float] = None
    contrast_snr: Optional[float] = None
    clipped: bool = False
    overload_0107: bool = False


@dataclass
class RunSidecar:
    """Standard Stage-1+ run document."""

    schema_version: str = "1.0"
    experiment: Optional[str] = None
    method_name: Optional[str] = None
    series_id: Optional[str] = None
    replicate_kind: Optional[str] = None
    passed: Optional[bool] = None
    provenance: dict[str, Any] = field(default_factory=dict)
    ls55_optics: dict[str, Any] = field(default_factory=dict)
    optical_path_config: dict[str, Any] = field(default_factory=dict)
    excitation_source_config: dict[str, Any] = field(default_factory=dict)
    auxiliary_state: dict[str, Any] = field(default_factory=dict)
    sample: dict[str, Any] = field(default_factory=dict)
    review_analysis: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra", {}) or {}
        # Flatten optional caller extras at top level without clobbering keys.
        for key, value in extra.items():
            if key not in data:
                data[key] = value
        return data

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path


def build_run_sidecar(
    *,
    experiment: str,
    method_name: Optional[str] = None,
    series_id: Optional[str] = None,
    replicate_kind: Optional[str] = None,
    passed: Optional[bool] = None,
    operator: Optional[str] = None,
    script_name: Optional[str] = None,
    instrument: Optional[dict[str, Any]] = None,
    optics: Optional[dict[str, Any]] = None,
    optical_path: Optional[OpticalPathConfig | dict[str, Any]] = None,
    excitation_source: Optional[ExcitationSourceConfig | dict[str, Any]] = None,
    auxiliary_state: Optional[dict[str, Any]] = None,
    sample: Optional[SampleMetadata | dict[str, Any]] = None,
    review: Optional[ReviewAnalysis | dict[str, Any]] = None,
    artifacts: Optional[dict[str, Any]] = None,
    raw_log: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    warnings: Optional[list[str]] = None,
    errors: Optional[list[str]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> RunSidecar:
    """Assemble a §7-compliant sidecar with UTC provenance."""
    now = datetime.now(timezone.utc).isoformat()
    inst = instrument or {}
    if isinstance(optical_path, OpticalPathConfig):
        path_cfg = asdict(optical_path)
    elif optical_path is None:
        path_cfg = asdict(OpticalPathConfig())
    else:
        path_cfg = dict(optical_path)

    if isinstance(excitation_source, ExcitationSourceConfig):
        src_cfg = asdict(excitation_source)
    elif excitation_source is None:
        src_cfg = asdict(ExcitationSourceConfig())
    else:
        src_cfg = dict(excitation_source)

    if isinstance(sample, SampleMetadata):
        sample_cfg = asdict(sample)
    elif sample is None:
        sample_cfg = asdict(SampleMetadata())
    else:
        sample_cfg = dict(sample)

    if isinstance(review, ReviewAnalysis):
        review_cfg = asdict(review)
    elif review is None:
        review_cfg = {}
    else:
        review_cfg = dict(review)

    art = dict(artifacts or {})
    if raw_log is not None:
        art.setdefault("raw_log", str(raw_log))
        digest = sha256_file(Path(raw_log))
        if digest:
            art["raw_log_sha256"] = digest

    return RunSidecar(
        experiment=experiment,
        method_name=method_name,
        series_id=series_id,
        replicate_kind=replicate_kind,
        passed=passed,
        provenance={
            "utc": now,
            "operator": operator,
            "git_commit": git_commit_hash(repo_root),
            "script_name": script_name,
            "instrument_model": inst.get("model", "55"),
            "firmware": inst.get("revision") or inst.get("firmware"),
            "serial": inst.get("serial") or inst.get("$SN"),
        },
        ls55_optics=dict(optics or {}),
        optical_path_config=path_cfg,
        excitation_source_config=src_cfg,
        auxiliary_state=dict(auxiliary_state or {}),
        sample=sample_cfg,
        review_analysis=review_cfg,
        artifacts=art,
        warnings=list(warnings or []),
        errors=list(errors or []),
        extra=dict(extra or {}),
    )
