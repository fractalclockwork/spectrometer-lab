"""Unit tests for LS 55 framing helpers."""

from ls55.protocol import (
    Record,
    Transaction,
    decode_accessories,
    encode_command,
    parse_es_position,
    parse_status_payload,
)


def test_encode_command_adds_dollar_and_cr():
    assert encode_command("ST") == b"$ST\r"
    assert encode_command("$ES 1") == b"$ES 1\r"


def test_record_parse_code_and_del_data():
    code = Record.parse(b"0000\r\n")
    assert code.is_code and code.code == "0000"

    data = Record.parse(b"\x7f55,A1,0000\r\n")
    assert not data.is_code
    assert data.data == "55,A1,0000"

    # Live glitch prefix before a code record.
    glitch = Record.parse(b"\xb50000\r\n")
    assert glitch.is_code and glitch.code == "0000"

    # Live glitch replacing one digit inside a 4-byte code (seen on $GM final).
    mid = Record.parse(b"000\xb5\r\n")
    assert mid.is_code and mid.code == "0000"


def test_transaction_complete_single_and_multi():
    me = Transaction(command="$ME")
    me.records.append(Record.parse(b"0000\r\n"))
    assert me.complete

    busy = Transaction(command="$ST")
    busy.records.append(Record.parse(b"0110\r\n"))
    assert busy.complete

    multi = Transaction(command="$ST")
    multi.records.append(Record.parse(b"0000\r\n"))
    assert not multi.complete
    multi.records.append(Record.parse(b"\x7f55,A1\r\n"))
    assert not multi.complete
    multi.records.append(Record.parse(b"0000\r\n"))
    assert multi.complete

    es_set = Transaction(command="$ES 1")
    es_set.records.append(Record.parse(b"0000\r\n"))
    assert not es_set.complete  # engine accepts via prompted idle


def test_scan_complete_waits_for_pad_after_status_ack():
    """Live $SC: 0000, status, 0000, data…-9999, 0000 — mid 0000 is not done."""
    sc = Transaction(command="$SC 1")
    sc.records.append(Record.parse(b"0000\r\n"))
    assert not sc.complete
    sc.records.append(
        Record.parse(b"\x7f55.F1,1001,350.0,400.0,  120.019, 5.0, 5.0,   76,   2.0\r\n")
    )
    assert not sc.complete
    sc.records.append(Record.parse(b"0000\r\n"))
    assert not sc.complete  # must not finish before spectral points
    sc.records.append(Record.parse(b"\x7f1,2,3,4,5,6,7,8,9,10\r\n"))
    assert not sc.complete
    sc.records.append(
        Record.parse(b"\x7f11,12,-9999,-9999,-9999,-9999,-9999,-9999,-9999,-9999\r\n")
    )
    assert not sc.complete
    sc.records.append(Record.parse(b"0000\r\n"))
    assert sc.complete


def test_parse_status_and_es():
    info = parse_status_payload("55,A1,0000,365.0,435.0")
    assert info.model == "55"
    assert info.revision == "A1"

    live = parse_status_payload(
        "55.F1,0001,365.0,435.0,  480.019,10.0,10.0,  100,  100, 1,   16"
    )
    assert live.model == "55"
    assert live.revision == "F1"
    assert live.ms == 0 and live.mq == 0 and live.dc == 0 and live.fl == 1
    assert live.ex_nm == 365.0 and live.em_nm == 435.0
    assert live.speed == 480 and live.response == 19
    assert live.ex_slit == 10.0 and live.em_slit == 10.0
    assert live.gate_ms == 1.0 and live.delay_ms == 1.0
    assert live.flashcount == 1 and live.cycle_ms == 16

    glitch = parse_status_payload(
        "55.F1,0001,365.0,435.0,  480.019,10.0,10.0,  100,   100,\x01 1,   16"
    )
    assert glitch.flashcount == 1
    assert glitch.speed == 480 and glitch.response == 19

    manual = parse_status_payload(
        "55,A1,0000,365.0,435.0,   0,  1, 10.0,  1.0,0.00,0.00,  1,20.0"
    )
    assert manual.speed == 0 and manual.response == 1
    assert manual.ex_slit == 10.0 and manual.em_slit == 1.0
    assert manual.flashcount == 1 and manual.cycle_ms == 20

    txn = Transaction(command="$ES")
    txn.records.append(Record.parse(b"0000\r\n"))
    txn.records.append(Record.parse(b"\x7f1\r\n"))
    txn.records.append(Record.parse(b"0000\r\n"))
    assert parse_es_position(txn) == 1


def test_decode_accessories_named_and_extra():
    info = decode_accessories("0,0,1,1,0,0,0,0,0,0,0,0,0")
    assert info.flags["excitation_polarizer"] is True
    assert info.flags["emission_polarizer"] is True
    assert info.flags["cell_holder"] is False
    assert info.extra_bits == [0]
    assert sum(1 for v in info.flags.values() if v) == 2

    # Live glitch: comma → 0xb5 → U+FFFD between first two zeros.
    glitched = decode_accessories("0\ufffd0,1,1,0,0,0,0,0,0,0,0,0")
    assert glitched.flags["excitation_polarizer"] is True
    assert glitched.flags["emission_polarizer"] is True
    assert glitched.flags["emission_mirror"] is False
    assert glitched.flags["plate_reader"] is False


def test_duplicate_initial_codes_wait_for_status_data():
    txn = Transaction(command="$ST")
    txn.records.append(Record.parse(b"\xb50000\r\n"))
    txn.records.append(Record.parse(b"0000\r\n"))
    assert not txn.complete
    txn.records.append(
        Record.parse(b"\x7f55.F1,0001,365.0,435.0\r\n")
    )
    assert not txn.complete
    txn.records.append(Record.parse(b"0000\r\n"))
    assert txn.complete

