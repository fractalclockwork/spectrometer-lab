"""Unit tests for scan status / point parsers."""

from ls55.scan import parse_scan_points, parse_scan_status, wavelengths


def test_wavelengths():
    assert wavelengths(400.0, 2.0, 3) == [400.0, 402.0, 404.0]


def test_parse_scan_points_skips_status_and_pad():
    records = [
        "55.F1,1000,350.0,400.0,120,0,5.0,5.0,76,2.0",
        "1,2,3,4,5,6,7,8,9,10",
        "11,12!,-9999,-9999,-9999,-9999,-9999,-9999,-9999,-9999",
    ]
    assert parse_scan_points(records) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]


def test_parse_scan_status_live_style():
    status = parse_scan_status(
        "55.F1,1001,350.0,400.0,  120.019, 5.0, 5.0,   76,   2.0"
    )
    assert status.revision == "F1"
    assert status.mx == 1
    assert status.ex_nm == 350.0
    assert status.em_nm == 400.0
    assert status.speed == 120
    assert status.max_points == 76
    assert status.data_interval == 2.0
