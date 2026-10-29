"""Canonical hex dump formatting for serial TX/RX logs."""

from __future__ import annotations


def hexdump(data: bytes, *, width: int = 16, base: int = 0) -> str:
    """
    Format bytes as classic hex dump lines:

        00000000  24 53 54 0d  ...                           |$ST.|
    """
    if not data:
        return f"{base:08x}  (empty)\n"
    lines: list[str] = []
    for offset in range(0, len(data), width):
        chunk = data[offset : offset + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        # Pad hex column to fixed width (3 chars per byte minus trailing space).
        hex_width = width * 3 - 1
        hex_part = hex_part.ljust(hex_width)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + offset:08x}  {hex_part}  |{ascii_part}|")
    return "\n".join(lines) + "\n"
