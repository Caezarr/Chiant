from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boring.position import Position
from boring.position_readiness import run_position_check, write_report


def test_position_check_passes_for_static_position():
    report = run_position_check(
        _StaticProvider(Position(50.6371, 3.0633, "static")),
        mode="static",
        expected_lat=50.6371,
        expected_lon=3.0633,
        now=_now(),
    )

    assert report.passed is True
    assert report.source == "static"
    assert report.failures == []


def test_position_check_fails_when_position_is_missing():
    report = run_position_check(_StaticProvider(None), mode="gpsd")

    assert report.passed is False
    assert report.failures == ["position=missing"]


def test_position_check_rejects_wrong_source_for_mode():
    report = run_position_check(
        _StaticProvider(Position(50.6371, 3.0633, "static")),
        mode="gpsd",
    )

    assert report.passed is False
    assert "source=static/gpsd" in report.failures


def test_position_check_records_gpsd_endpoint():
    report = run_position_check(
        _StaticProvider(Position(50.6371, 3.0633, "gpsd")),
        mode="gpsd",
        gpsd_host="gps.local",
        gpsd_port=2948,
    )

    assert report.passed is True
    assert report.gpsd_host == "gps.local"
    assert report.gpsd_port == 2948


def test_position_check_rejects_static_coordinate_drift():
    report = run_position_check(
        _StaticProvider(Position(50.6400, 3.0633, "static")),
        mode="static",
        expected_lat=50.6371,
        expected_lon=3.0633,
    )

    assert report.passed is False
    assert any(failure.startswith("lat_delta=") for failure in report.failures)


def test_write_position_report_includes_passed(tmp_path: Path):
    report = run_position_check(
        _StaticProvider(Position(50.6371, 3.0633, "static")),
        mode="static",
        expected_lat=50.6371,
        expected_lon=3.0633,
        now=_now(),
    )
    output = tmp_path / "reports" / "position-check.json"

    write_report(report, output)

    assert '"passed": true' in output.read_text()


class _StaticProvider:
    def __init__(self, position: Position | None) -> None:
        self.position = position

    def current(self) -> Position | None:
        return self.position


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
