from __future__ import annotations

from boring.position import StaticPositionProvider, make_position_provider, parse_gpsd_tpv


def test_static_position_provider_returns_position():
    position = StaticPositionProvider(50.6371, 3.0633).current()

    assert position is not None
    assert position.lat == 50.6371
    assert position.lon == 3.0633
    assert position.source == "static"


def test_static_position_provider_missing_coords():
    assert StaticPositionProvider(None, 3.0633).current() is None


def test_parse_gpsd_tpv_valid():
    position = parse_gpsd_tpv('{"class":"TPV","lat":50.1,"lon":3.2}')

    assert position is not None
    assert position.lat == 50.1
    assert position.lon == 3.2
    assert position.source == "gpsd"


def test_parse_gpsd_tpv_ignores_non_position():
    assert parse_gpsd_tpv('{"class":"VERSION"}') is None
    assert parse_gpsd_tpv("not-json") is None


def test_make_position_provider_defaults_static():
    provider = make_position_provider("static", 1.0, 2.0)

    assert isinstance(provider, StaticPositionProvider)
