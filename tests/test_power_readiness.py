from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boring.power import BatteryStatus
from boring.power_readiness import run_power_check, write_report


def test_power_check_passes_with_known_battery_and_runtime():
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(95, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        required_runtime_hours=10,
        now=_now(),
    )

    assert report.passed is True
    assert report.battery_percent == 95
    assert report.critical_reserve_wh == 10
    assert report.available_battery_wh == 85
    assert report.estimated_runtime_hours == 10.625
    assert report.battery_critical_percent == 10
    assert report.failures == []


def test_power_check_fails_without_battery_sensor():
    report = run_power_check(
        monitor=_StaticPower(None),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
    )

    assert report.passed is False
    assert "battery=missing" in report.failures


def test_power_check_fails_when_battery_is_critical():
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(8, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        battery_critical_percent=10,
    )

    assert report.passed is False
    assert "battery_percent=8/10" in report.failures


def test_power_check_fails_when_runtime_is_short():
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(80, True, "bat")),
        battery_capacity_wh=40,
        estimated_draw_watts=8,
        required_runtime_hours=10,
    )

    assert report.passed is False
    assert report.critical_reserve_wh == 4
    assert report.available_battery_wh == 28
    assert "runtime=3.5/10.0h" in report.failures


def test_power_check_uses_capacity_above_critical_threshold_for_runtime():
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(70, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        required_runtime_hours=10,
    )

    assert report.passed is False
    assert report.critical_reserve_wh == 10
    assert report.available_battery_wh == 60
    assert report.estimated_runtime_hours == 7.5
    assert "runtime=7.5/10.0h" in report.failures


def test_write_power_report_includes_passed(tmp_path: Path):
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(95, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        now=_now(),
    )
    output = tmp_path / "reports" / "power-check.json"

    write_report(report, output)

    assert '"passed": true' in output.read_text()
    assert '"critical_reserve_wh": 10.0' in output.read_text()
    assert '"battery_critical_percent": 10' in output.read_text()


class _StaticPower:
    def __init__(self, status: BatteryStatus | None) -> None:
        self.status = status

    def read(self) -> BatteryStatus | None:
        return self.status


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
