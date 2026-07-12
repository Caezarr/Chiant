"""Validation terrain limitee dans le temps pour la box headless."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from boring.capture import CameraProbeResult, probe_camera
from boring.config import BoxConfig
from boring.network import NetworkMonitor, NetworkStatus
from boring.power import (
    BatteryStatus,
    LinuxPowerSupplyMonitor,
    LinuxThermalMonitor,
    ThermalStatus,
)


@dataclass(frozen=True)
class BurnInSample:
    ts: float
    camera_ok: bool
    camera_error: str | None
    battery_percent: int | None
    battery_charging: bool | None
    battery_source: str | None
    temp_c: float | None
    thermal_source: str | None
    thermal_label: str | None
    network_online: bool
    network_error: str | None


@dataclass(frozen=True)
class BurnInReport:
    started_at: float
    ended_at: float
    requested_duration_seconds: float | None
    duration_seconds: float
    interval_seconds: float | None
    max_sample_gap_seconds: float | None
    sample_count: int
    camera_failures: int
    network_failures: int
    start_battery_percent: int | None
    end_battery_percent: int | None
    min_battery_percent: int | None
    battery_delta_percent: int | None
    charging_seen: bool
    discharging_seen: bool
    battery_low_percent: int
    battery_critical_percent: int
    thermal_warning_c: float
    thermal_critical_c: float
    max_temp_c: float | None
    thermal_warning_seen: bool
    thermal_critical_seen: bool
    battery_low_seen: bool
    battery_critical_seen: bool
    passed: bool


class BoxBurnInRunner:
    """Sonde la box pendant une duree courte et produit un rapport exploitable."""

    def __init__(
        self,
        config: BoxConfig,
        *,
        camera_probe: Callable[[int], CameraProbeResult] = probe_camera,
        power: LinuxPowerSupplyMonitor | None = None,
        thermal: LinuxThermalMonitor | None = None,
        network: NetworkMonitor | None = None,
        clock: Callable[[], float] = time.time,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.camera_probe = camera_probe
        self.power = power or LinuxPowerSupplyMonitor()
        self.thermal = thermal or LinuxThermalMonitor()
        self.network = network or NetworkMonitor(config.network_probe_target)
        self.clock = clock
        self.sleeper = sleeper

    def run(
        self,
        *,
        duration_seconds: float,
        interval_seconds: float,
        output_dir: Path,
    ) -> BurnInReport:
        output_dir.mkdir(parents=True, exist_ok=True)
        samples_path = output_dir / "samples.jsonl"
        report_path = output_dir / "report.json"
        started_at = self.clock()
        deadline = started_at + duration_seconds
        samples: list[BurnInSample] = []

        with samples_path.open("w") as fp:
            while True:
                sample = self.sample()
                samples.append(sample)
                fp.write(json.dumps(asdict(sample), sort_keys=True) + "\n")
                fp.flush()
                if self.clock() >= deadline:
                    break
                self.sleeper(max(0.0, interval_seconds))

        ended_at = self.clock()
        report = build_report(
            samples,
            started_at=started_at,
            ended_at=ended_at,
            requested_duration_seconds=duration_seconds,
            interval_seconds=interval_seconds,
            config=self.config,
        )
        report_path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n")
        return report

    def sample(self) -> BurnInSample:
        camera = self.camera_probe(self.config.camera_device)
        battery = self.power.read()
        thermal = self.thermal.read()
        network = self.network.check()
        return make_sample(
            ts=self.clock(),
            camera=camera,
            battery=battery,
            thermal=thermal,
            network=network,
        )


def make_sample(
    *,
    ts: float,
    camera: CameraProbeResult,
    battery: BatteryStatus | None,
    thermal: ThermalStatus | None,
    network: NetworkStatus,
) -> BurnInSample:
    return BurnInSample(
        ts=ts,
        camera_ok=camera.ok,
        camera_error=camera.error,
        battery_percent=battery.percent if battery else None,
        battery_charging=battery.charging if battery else None,
        battery_source=battery.source if battery else None,
        temp_c=thermal.temp_c if thermal else None,
        thermal_source=thermal.source if thermal else None,
        thermal_label=thermal.label if thermal else None,
        network_online=network.online,
        network_error=network.error,
    )


def build_report(
    samples: list[BurnInSample],
    *,
    started_at: float,
    ended_at: float,
    requested_duration_seconds: float | None = None,
    interval_seconds: float | None = None,
    config: BoxConfig,
) -> BurnInReport:
    battery_values = [
        sample.battery_percent for sample in samples if sample.battery_percent is not None
    ]
    temp_values = [sample.temp_c for sample in samples if sample.temp_c is not None]
    camera_failures = sum(1 for sample in samples if not sample.camera_ok)
    network_failures = sum(1 for sample in samples if not sample.network_online)
    min_battery = min(battery_values) if battery_values else None
    start_battery = battery_values[0] if battery_values else None
    end_battery = battery_values[-1] if battery_values else None
    battery_delta = (
        end_battery - start_battery
        if start_battery is not None and end_battery is not None
        else None
    )
    charging_seen = any(sample.battery_charging is True for sample in samples)
    discharging_seen = any(sample.battery_charging is False for sample in samples)
    max_temp = max(temp_values) if temp_values else None
    thermal_warning_seen = max_temp is not None and max_temp >= config.thermal_warning_c
    thermal_critical_seen = max_temp is not None and max_temp >= config.thermal_critical_c
    battery_low_seen = min_battery is not None and min_battery <= config.battery_low_percent
    battery_critical_seen = (
        min_battery is not None and min_battery <= config.battery_critical_percent
    )
    duration_seconds = max(0.0, ended_at - started_at)
    requested_duration_ok = requested_duration_seconds is None or (
        requested_duration_seconds > 0 and duration_seconds + 1.0 >= requested_duration_seconds
    )
    passed = (
        bool(samples)
        and duration_seconds > 0
        and requested_duration_ok
        and camera_failures == 0
        and network_failures == 0
        and not thermal_critical_seen
        and not battery_critical_seen
    )
    return BurnInReport(
        started_at=started_at,
        ended_at=ended_at,
        requested_duration_seconds=requested_duration_seconds,
        duration_seconds=duration_seconds,
        interval_seconds=interval_seconds,
        max_sample_gap_seconds=_max_sample_gap_seconds(interval_seconds),
        sample_count=len(samples),
        camera_failures=camera_failures,
        network_failures=network_failures,
        start_battery_percent=start_battery,
        end_battery_percent=end_battery,
        min_battery_percent=min_battery,
        battery_delta_percent=battery_delta,
        charging_seen=charging_seen,
        discharging_seen=discharging_seen,
        battery_low_percent=config.battery_low_percent,
        battery_critical_percent=config.battery_critical_percent,
        thermal_warning_c=config.thermal_warning_c,
        thermal_critical_c=config.thermal_critical_c,
        max_temp_c=max_temp,
        thermal_warning_seen=thermal_warning_seen,
        thermal_critical_seen=thermal_critical_seen,
        battery_low_seen=battery_low_seen,
        battery_critical_seen=battery_critical_seen,
        passed=passed,
    )


def _max_sample_gap_seconds(interval_seconds: float | None) -> float | None:
    if interval_seconds is None or interval_seconds <= 0:
        return None
    return max(interval_seconds * 1.5, interval_seconds + 5.0)
