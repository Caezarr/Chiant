"""Runtime power readiness check for a Boring Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from boring.power import (
    BatteryStatus,
    LinuxPowerSupplyMonitor,
    estimate_available_capacity_wh,
    estimate_runtime_hours,
)


@dataclass(frozen=True)
class PowerCheckReport:
    passed: bool
    battery_percent: int | None
    charging: bool | None
    source: str | None
    battery_capacity_wh: float | None
    available_battery_wh: float | None
    estimated_draw_watts: float
    estimated_runtime_hours: float | None
    required_runtime_hours: float
    checked_at: str
    failures: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def run_power_check(
    *,
    monitor: LinuxPowerSupplyMonitor | None = None,
    battery_capacity_wh: float | None = None,
    estimated_draw_watts: float = 8.0,
    required_runtime_hours: float = 10.0,
    battery_critical_percent: int = 10,
    now: datetime | None = None,
) -> PowerCheckReport:
    status = (monitor or LinuxPowerSupplyMonitor()).read()
    available_battery_wh = estimate_available_capacity_wh(
        battery_capacity_wh,
        status.percent if status else None,
    )
    runtime_hours = estimate_runtime_hours(available_battery_wh, estimated_draw_watts)
    checked_at = (now or datetime.now(timezone.utc)).isoformat()
    failures = _power_failures(
        status,
        runtime_hours=runtime_hours,
        required_runtime_hours=required_runtime_hours,
        battery_critical_percent=battery_critical_percent,
    )
    return PowerCheckReport(
        passed=not failures,
        battery_percent=status.percent if status else None,
        charging=status.charging if status else None,
        source=status.source if status else None,
        battery_capacity_wh=battery_capacity_wh,
        available_battery_wh=available_battery_wh,
        estimated_draw_watts=estimated_draw_watts,
        estimated_runtime_hours=runtime_hours,
        required_runtime_hours=required_runtime_hours,
        checked_at=checked_at,
        failures=failures,
    )


def write_report(report: PowerCheckReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _power_failures(
    status: BatteryStatus | None,
    *,
    runtime_hours: float | None,
    required_runtime_hours: float,
    battery_critical_percent: int,
) -> list[str]:
    failures = []
    if status is None:
        failures.append("battery=missing")
    else:
        if status.percent is None:
            failures.append("battery_percent=missing")
        elif status.percent <= battery_critical_percent:
            failures.append(f"battery_percent={status.percent}/{battery_critical_percent}")
        if status.charging is None:
            failures.append("charging=unknown")
    if runtime_hours is None:
        failures.append("runtime=missing")
    elif runtime_hours < required_runtime_hours:
        failures.append(f"runtime={runtime_hours:.1f}/{required_runtime_hours:.1f}h")
    return failures
