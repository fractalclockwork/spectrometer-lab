"""LS 55 RS-232 framing helpers (manual pp. 125–126, 148–154)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

DC1 = b"\x11"
DC3 = b"\x13"
DEL = 0x7F
CR = b"\r"
LF = b"\n"
CRLF = b"\r\n"

CODE_RE = re.compile(rb"^\d{4}$")

# Codes that close a transaction when they appear as a bare record.
# Special dialogue codes 1000/1001/1002 are not treated as Stage-1 completions.
ORDINARY_COMPLETION_CODES = frozenset(
    {
        "0000",
        "0002",
        "0022",
        "0099",
        "0100",
        "0106",
        "0107",
        "0108",
        "0110",
        "0111",
        "0112",
    }
)


@dataclass
class Record:
    """One CR+LF-terminated instrument record."""

    raw: bytes
    is_code: bool
    code: Optional[str] = None
    data: Optional[str] = None  # DEL stripped, UTF-8 with replacement

    @classmethod
    def parse(cls, raw: bytes) -> "Record":
        body = raw
        if body.endswith(CRLF):
            body = body[:-2]
        elif body.endswith(CR) or body.endswith(LF):
            body = body[:-1]

        # Live captures sometimes inject glitch bytes (e.g. 0xb5) around codes.
        cleaned = _strip_leading_junk(body)
        code = _coerce_status_code(cleaned)
        if code is not None:
            return cls(raw=raw, is_code=True, code=code)

        data_bytes = cleaned
        if data_bytes[:1] == bytes([DEL]):
            data_bytes = data_bytes[1:]
        return cls(
            raw=raw,
            is_code=False,
            data=data_bytes.decode("ascii", errors="replace"),
        )


@dataclass
class Transaction:
    """Complete response to one command (initial code … final code)."""

    command: str
    records: list[Record] = field(default_factory=list)

    @property
    def initial_code(self) -> Optional[str]:
        for rec in self.records:
            if rec.is_code:
                return rec.code
        return None

    @property
    def final_code(self) -> Optional[str]:
        for rec in reversed(self.records):
            if rec.is_code:
                return rec.code
        return None

    @property
    def data_records(self) -> list[str]:
        return [r.data for r in self.records if not r.is_code and r.data is not None]

    @property
    def mnemonic(self) -> str:
        body = self.command.strip().lstrip("$").upper()
        return body.split()[0] if body else ""

    @property
    def complete(self) -> bool:
        """
        A transaction is complete when the final 4-digit code has arrived.

        Rules:
        - Two or more code records → complete (initial + final).
        - One non-0000 code and no data → complete (busy/error or $ME status).
        - One 0000 and no data → incomplete here; the engine may accept it as a
          single-code success after a prompted idle (e.g. $ES 1).
        - One code plus data → waiting for the final code.
        - Scan/time-drive ($SC / $TD): live units may send 0000 after the
          status header before spectral points. Do not complete until a
          ``-9999`` pad has been seen, then a following ordinary code.
        """
        codes = [r for r in self.records if r.is_code]
        if not codes:
            return False
        if self.mnemonic in {"SC", "TD"}:
            return self._scan_like_complete(codes)
        if len(codes) >= 2:
            # Initial + final with data in between → complete.
            if self.data_records:
                # Need a code after the data (final), not only codes before data.
                # Count codes after the first data record.
                seen_data = False
                codes_after_data = 0
                for rec in self.records:
                    if not rec.is_code and rec.data is not None:
                        seen_data = True
                    elif rec.is_code and seen_data:
                        codes_after_data += 1
                return codes_after_data >= 1 and codes[-1].code in ORDINARY_COMPLETION_CODES
            # Live units may emit a junk-prefixed 0000 then a clean 0000
            # before STATUS data. Do not close yet on duplicate success codes
            # with no data (engine may accept via prompted idle).
            if all(c.code == "0000" for c in codes):
                return False
            return codes[-1].code in ORDINARY_COMPLETION_CODES
        if self.data_records:
            return False
        only = codes[0].code
        if only != "0000":
            return only in ORDINARY_COMPLETION_CODES
        # Sole 0000: $ME treats this as the NVM status result.
        return self.mnemonic == "ME"

    def _scan_like_complete(self, codes: list[Record]) -> bool:
        # Immediate reject / abort with no payload.
        if (
            len(codes) == 1
            and not self.data_records
            and codes[0].code in ORDINARY_COMPLETION_CODES
            and codes[0].code != "0000"
        ):
            return True
        if not self._scan_pad_seen():
            return False
        # Final ordinary code after the padded data record.
        seen_pad = False
        for rec in self.records:
            if not rec.is_code and rec.data is not None and "-9999" in rec.data:
                seen_pad = True
            elif rec.is_code and seen_pad:
                return rec.code in ORDINARY_COMPLETION_CODES
        return False

    def _scan_pad_seen(self) -> bool:
        return any(
            not r.is_code and r.data is not None and "-9999" in r.data
            for r in self.records
        )


# $AF flag order per Users Guide ~4232–4235.
ACCESSORY_NAMES: tuple[str, ...] = (
    "emission_mirror",
    "plate_reader",
    "excitation_polarizer",
    "emission_polarizer",
    "cell_holder",
    "well_plate_reader",
    "stirrer",
    "temperature_controller",
    "peristaltic_pump",
    "autosampler",
    "ffa_excitation",
    "ffa_emission",
)


@dataclass
class StatusInfo:
    model: str
    revision: str
    raw_payload: str
    fields: list[str]
    # Typed STATUS fields (Users Guide ~4284–4337); None if absent/unparseable.
    ms: Optional[int] = None
    mq: Optional[int] = None
    dc: Optional[int] = None
    fl: Optional[int] = None
    ex_nm: Optional[float] = None
    em_nm: Optional[float] = None
    speed: Optional[int] = None
    response: Optional[int] = None
    ex_slit: Optional[float] = None
    em_slit: Optional[float] = None
    gate_ms: Optional[float] = None  # converted from 0.01 ms units
    delay_ms: Optional[float] = None
    flashcount: Optional[int] = None
    cycle_ms: Optional[int] = None


@dataclass
class AccessoriesInfo:
    """Named decode of an `$AF` comma-separated 0/1 flag string."""

    raw: str
    flags: dict[str, bool]
    extra_bits: list[int] = field(default_factory=list)


def encode_command(mnemonic_and_args: str) -> bytes:
    """Build a command frame: '$' + body + CR (no LF)."""
    body = mnemonic_and_args.strip()
    if not body.startswith("$"):
        body = "$" + body
    encoded = body.encode("ascii") + CR
    if len(encoded) > 128:
        raise ValueError(f"command exceeds 128-byte limit: {len(encoded)}")
    return encoded


def _strip_leading_junk(body: bytes) -> bytes:
    """Drop leading bytes that are not printable ASCII or DEL."""
    i = 0
    while i < len(body):
        b = body[i]
        if b == DEL or 32 <= b < 127:
            break
        i += 1
    return body[i:]


def _coerce_status_code(body: bytes) -> Optional[str]:
    """
    Return a 4-digit status code if ``body`` is a clean or glitch-corrupted code.

    Live links sometimes replace one digit with a high byte (e.g. ``000\\xb5``
    instead of ``0000``). Rebuild 4-byte frames by treating non-printable noise
    as a corrupted ``0``; refuse if any printable non-digit is present.
    """
    if CODE_RE.fullmatch(body):
        return body.decode("ascii")
    if len(body) != 4:
        return None
    rebuilt = bytearray()
    noise = 0
    for b in body:
        if 48 <= b <= 57:  # 0-9
            rebuilt.append(b)
        elif 32 <= b < 127 or b == DEL:
            return None
        else:
            rebuilt.append(48)  # assume corrupted digit was '0'
            noise += 1
    if noise and CODE_RE.fullmatch(bytes(rebuilt)):
        return bytes(rebuilt).decode("ascii")
    return None


def find_status_payload(data_records: list[str]) -> Optional[str]:
    """Return the first data record whose payload starts with model id 55."""
    for data in data_records:
        text = data.lstrip()
        if text.startswith("55.") or text.startswith("55,"):
            return data
        if text.startswith("55"):
            return data
    return None


def parse_status_payload(payload: str) -> StatusInfo:
    """
    Parse STATUS data after DEL strip.

    Accepts manual-style ``55,<rev>,...`` and live firmware ``55.F1,...``.
    Unpacks typed fields per Users Guide ~4284–4337. Live units often join
    ``<speed>.<response>`` with a period instead of a comma (same quirk as
    scan headers).
    """
    text = payload.lstrip()
    if text.startswith("55."):
        # 55.<rev>,<rest...>
        rest = text[3:]
        if "," in rest:
            revision, remainder = rest.split(",", 1)
            fields = ["55", revision.strip()] + [
                p.strip() for p in remainder.split(",")
            ]
        else:
            revision = rest.strip()
            fields = ["55", revision]
        info = StatusInfo(
            model="55", revision=revision.strip(), raw_payload=payload, fields=fields
        )
        _unpack_status_fields(info)
        return info

    fields = [p.strip() for p in text.split(",")]
    if not fields or fields[0] != "55":
        raise ValueError(f"STATUS model id is not 55: {payload!r}")
    revision = fields[1] if len(fields) > 1 else ""
    info = StatusInfo(
        model="55", revision=revision, raw_payload=payload, fields=fields
    )
    _unpack_status_fields(info)
    return info


def _parse_int_field(token: str) -> Optional[int]:
    """First integer in token; ignores glitch bytes and trailing ``.0``."""
    match = re.search(r"-?\d+", token)
    if not match:
        return None
    return int(match.group(0))


def _parse_float_field(token: str) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", token)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _unpack_status_fields(info: StatusInfo) -> None:
    """Fill typed StatusInfo attributes from ``info.fields`` after model/rev."""
    # fields[0]=55, fields[1]=rev, then manual STATUS body fields.
    body = info.fields[2:]
    if not body:
        return

    mode = body[0].replace(" ", "")
    if re.fullmatch(r"\d{1,4}", mode):
        padded = mode.zfill(4)
        try:
            info.ms = int(padded[0])
            info.mq = int(padded[1])
            info.dc = int(padded[2])
            info.fl = int(padded[3])
        except ValueError:
            pass
        body = body[1:]

    if len(body) >= 1:
        info.ex_nm = _parse_float_field(body[0])
    if len(body) >= 2:
        info.em_nm = _parse_float_field(body[1])

    idx = 2
    if len(body) > idx:
        speed_tok = body[idx].replace(" ", "")
        # Live firmware joins speed.response: "480.019" or "120.019".
        # Wavelength-like "365.0" is only one fractional digit — not this form.
        m = re.fullmatch(r"(-?\d+)\.(\d{2,})", speed_tok)
        if m:
            info.speed = int(m.group(1))
            info.response = int(m.group(2))
            idx += 1
        else:
            info.speed = _parse_int_field(speed_tok)
            idx += 1
            if len(body) > idx and info.response is None:
                nxt = body[idx].strip()
                # Response is an integer field; slits look like xx.x
                if re.fullmatch(r"-?\d+", nxt.replace(" ", "")):
                    info.response = _parse_int_field(nxt)
                    idx += 1

    if len(body) > idx:
        info.ex_slit = _parse_float_field(body[idx])
        idx += 1
    if len(body) > idx:
        info.em_slit = _parse_float_field(body[idx])
        idx += 1

    # gate / delay are integers in 0.01 ms units (fixtures may show 0.00).
    if len(body) > idx:
        gate_raw = _parse_int_field(body[idx])
        if gate_raw is not None:
            info.gate_ms = gate_raw / 100.0
        idx += 1
    if len(body) > idx:
        delay_raw = _parse_int_field(body[idx])
        if delay_raw is not None:
            info.delay_ms = delay_raw / 100.0
        idx += 1
    if len(body) > idx:
        info.flashcount = _parse_int_field(body[idx])
        idx += 1
    if len(body) > idx:
        info.cycle_ms = _parse_int_field(body[idx])


def sanitize_af_bits(bits: str) -> str:
    """
    Repair live `$AF` glitches before CSV split.

    Observed: a comma replaced by ``0xb5`` becomes U+FFFD under ASCII
    ``errors=replace``, yielding ``0\\ufffd0,1,1,...`` instead of ``0,0,1,1,...``.
    """
    return bits.replace("\ufffd", ",").replace("\x01", ",")


def decode_accessories(bits: str) -> AccessoriesInfo:
    """
    Map an `$AF` CSV of 0/1 flags to named accessories.

    Manual lists 12 flags. Extra trailing tokens (seen live as a 13th ``0``)
    are preserved in ``extra_bits`` and ignored for naming.
    """
    cleaned = sanitize_af_bits(bits)
    values: list[int] = []
    for t in cleaned.split(","):
        t = t.strip()
        if t in {"0", "1"}:
            values.append(int(t))

    flags = {
        name: bool(values[i]) if i < len(values) else False
        for i, name in enumerate(ACCESSORY_NAMES)
    }
    extra = values[len(ACCESSORY_NAMES) :]
    return AccessoriesInfo(raw=bits, flags=flags, extra_bits=extra)


def parse_es_position(transaction: Transaction) -> Optional[int]:
    """Extract excitation-shutter position from an $ES transaction."""
    for data in transaction.data_records:
        text = data.strip()
        if text.isdigit():
            return int(text)
        # Some firmware may echo 'position' alone or with trailing junk.
        match = re.search(r"\b([01])\b", text)
        if match:
            return int(match.group(1))
    return None


def me_status_code(transaction: Transaction) -> Optional[str]:
    """$ME reports NVM state as the transaction code (0000 / 0108 / 0106)."""
    return transaction.final_code
