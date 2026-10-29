"""LS 55 scan ($SC) status and ASCII data-record parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ls55.protocol import find_status_payload

_PAD = -9999
_POINT_RE = re.compile(r"^(-?\d+)!?$")


@dataclass
class ScanStatus:
    """Parsed scan-status header (fields vary slightly by firmware)."""

    raw: str
    revision: str = ""
    mx: Optional[int] = None
    ex_nm: Optional[float] = None
    em_nm: Optional[float] = None
    speed: Optional[int] = None
    ex_slit: Optional[float] = None
    em_slit: Optional[float] = None
    max_points: Optional[int] = None
    data_interval: Optional[float] = None


def parse_scan_status(record: str) -> ScanStatus:
    """
    Parse a scan status data record.

    Accepts live ``55.<rev>,...`` and manual-style ``55,<rev>,...``.
    Field layout is best-effort: wavelength / interval / max-points are
    recovered by position heuristics when present.
    """
    text = record.lstrip()
    status = ScanStatus(raw=record)
    if text.startswith("55."):
        rest = text[3:]
        if "," in rest:
            rev, remainder = rest.split(",", 1)
        else:
            rev, remainder = rest, ""
        status.revision = rev.strip()
        fields = [p.strip() for p in remainder.split(",")] if remainder else []
    elif text.startswith("55,"):
        parts = [p.strip() for p in text.split(",")]
        status.revision = parts[1] if len(parts) > 1 else ""
        fields = parts[2:]
    else:
        raise ValueError(f"scan status does not start with 55: {record!r}")

    # Common layout after mode nibble field:
    # <ms mq dc fl>, ex, em, speed, response, ex_slit, em_slit, max_points, data_int
    if fields and re.fullmatch(r"\d{1,4}", fields[0].replace(" ", "")):
        mode = fields[0].replace(" ", "")
        if mode:
            try:
                status.mx = int(mode[0])
            except ValueError:
                pass
        fields = fields[1:]

    floats: list[float] = []
    ints: list[int] = []
    for f in fields:
        if not f or f.startswith("*"):
            continue
        try:
            if "." in f:
                floats.append(float(f))
            else:
                ints.append(int(f))
                floats.append(float(f))
        except ValueError:
            continue

    # Live scan header (observed):
    # 55.<rev>,<ms mq dc fl>,ex,em,<speed>.<response>,ex_slit,em_slit,max_pts,interval
    if len(fields) >= 2:
        try:
            status.ex_nm = float(fields[0])
            status.em_nm = float(fields[1])
        except ValueError:
            pass
    if len(fields) >= 3:
        # "  120.019" → speed 120, response 019
        speed_tok = fields[2].replace(" ", "")
        if "." in speed_tok:
            left, _, _right = speed_tok.partition(".")
            try:
                status.speed = int(left)
            except ValueError:
                pass
        else:
            try:
                status.speed = int(speed_tok)
            except ValueError:
                pass
    if len(fields) >= 5:
        try:
            status.ex_slit = float(fields[3])
            status.em_slit = float(fields[4])
        except ValueError:
            pass
    if len(fields) >= 6:
        try:
            status.max_points = int(fields[5].replace(" ", ""))
        except ValueError:
            pass
    if len(fields) >= 7:
        try:
            status.data_interval = float(fields[6])
        except ValueError:
            pass

    return status


def find_scan_status(data_records: list[str]) -> Optional[ScanStatus]:
    payload = find_status_payload(data_records)
    if payload is None:
        return None
    try:
        return parse_scan_status(payload)
    except ValueError:
        return None


def parse_scan_points(data_records: list[str]) -> list[int]:
    """
    Flatten ASCII scan data records into intensities.

    Skips the leading ``55…`` status record. Stops at the first ``-9999`` pad.
    Trailing ``!`` event markers are stripped.
    """
    points: list[int] = []
    started = False
    for rec in data_records:
        text = rec.lstrip()
        if not started:
            if text.startswith("55.") or text.startswith("55,") or text.startswith("55"):
                started = True
                continue
            # No status seen yet; treat as data if numeric.
        started = True
        for field in text.split(","):
            token = field.strip()
            if not token:
                continue
            match = _POINT_RE.fullmatch(token)
            if not match:
                # Non-numeric mid-stream: skip field rather than aborting.
                continue
            value = int(match.group(1))
            if value == _PAD:
                return points
            points.append(value)
    return points


def wavelengths(start_nm: float, interval_nm: float, n: int) -> list[float]:
    """Abscissa axis for a constant-interval scan starting at ``start_nm``."""
    if n < 0:
        raise ValueError("n must be >= 0")
    return [round(start_nm + i * interval_nm, 1) for i in range(n)]
