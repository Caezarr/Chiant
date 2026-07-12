from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boring.power import BatteryStatus
from boring.power_readiness import run_power_check, write_report


def test_power_check_passes_with_known_battery_and_runtime():
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(82, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        required_runtime_hours=10,
        now=_now(),
    )

    assert report.passed is True
    assert report.battery_percent == 82
    assert report.available_battery_wh == 82
    assert report.estimated_runtime_hours == 10.25
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
    assert report.available_battery_wh == 32
    assert "runtime=4.0/10.0h" in report.failures


def test_power_check_uses_current_battery_percent_for_runtime():
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(70, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        required_runtime_hours=10,
    )

    assert report.passed is False
    assert report.available_battery_wh == 70
    assert report.estimated_runtime_hours == 8.75
    assert "runtime=8.8/10.0h" in report.failures


def test_write_power_report_includes_passed(tmp_path: Path):
    report = run_power_check(
        monitor=_StaticPower(BatteryStatus(82, False, "bat")),
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        now=_now(),
    )
    output = tmp_path / "reports" / "power-check.json"

    write_report(report, output)

    assert '"passed": true' in output.read_text()


class _StaticPower:
    def __init__(self, status: BatteryStatus | None) -> None:
        self.status = status

    def read(self) -> BatteryStatus | None:
        return self.status


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
