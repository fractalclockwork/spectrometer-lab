"""Tests for canonical hex dump formatting."""

from ls55.hexdump import hexdump


def test_hexdump_empty():
    assert "(empty)" in hexdump(b"")


def test_hexdump_line():
    out = hexdump(b"$ST\r")
    assert "24 53 54 0d" in out
    assert "|$ST.|" in out
