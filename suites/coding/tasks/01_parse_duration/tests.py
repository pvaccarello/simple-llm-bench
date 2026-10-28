import pytest_shim as t
from solution import parse_duration


def test_basic():
    assert parse_duration("1h30m") == 5400
    assert parse_duration("45s") == 45
    assert parse_duration("0s") == 0


def test_spaces_and_case():
    assert parse_duration("2d 3h") == 183600
    assert parse_duration("  10m  ") == 600
    assert parse_duration("1W") == 604800
    assert parse_duration("1h 30M 15s") == 5415


def test_all_units():
    assert parse_duration("1w1d1h1m1s") == 604800 + 86400 + 3600 + 60 + 1
    assert parse_duration("100m") == 6000


def test_invalid_format():
    for bad in ["", "   ", "h", "5x", "-5m", "+5m", "1.5h", "10", "1 h", "abc"]:
        t.raises(ValueError, parse_duration, bad)


def test_invalid_order():
    for bad in ["1h1h", "30m1h", "1s1m", "1d1w"]:
        t.raises(ValueError, parse_duration, bad)
