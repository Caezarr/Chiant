from __future__ import annotations

import json
from pathlib import Path

from boring.burn_in import BoxBurnInRunner, BurnInSample, build_report, make_sample
from boring.capture import CameraProbeResult
from boring.config import BoxConfig
from boring.network import NetworkStatus
from boring.power import BatteryStatus, ThermalStatus


def test_make_sample_flattens_probe_statuses():
    sample = make_sample(
        ts=123.0,
        camera=CameraProbeResult(True, 0, width=640, height=480),
        battery=BatteryStatus(82, False, "/sys/class/power_supply/BAT0"),
        thermal=ThermalStatus(54.2, "/sys/class/thermal/thermal_zone0", "cpu-thermal"),
        network=NetworkStatus(True, "1.1.1.1:443"),
    )

    assert sample.camera_ok is True
    assert sample.battery_percent == 82
    assert sample.temp_c == 54.2
    assert sample.network_online is True


def test_build_report_passes_with_healthy_samples():
    report = build_report(
        [
            BurnInSample(
                ts=1,
                camera_ok=True,
                camera_error=None,
                battery_percent=80,
                battery_charging=False,
                battery_source="bat",
                temp_c=55,
                thermal_source="thermal",
                thermal_label="cpu",
                network_online=True,
                network_error=None,
            ),
            BurnInSample(
                ts=61,
                camera_ok=True,
                camera_error=None,
                battery_percent=84,
                battery_charging=True,
                battery_source="bat",
                temp_c=56,
                thermal_source="thermal",
                thermal_label="cpu",
                network_online=True,
                network_error=None,
            ),
        ],
        started_at=1,
        ended_at=61,
        config=BoxConfig(),
    )

    assert report.passed is True
    assert report.sample_count == 2
    assert report.start_battery_percent == 80
    assert report.end_battery_percent == 84
    assert report.min_battery_percent == 80
    assert report.battery_delta_percent == 4
    assert report.charging_seen is True
    assert report.discharging_seen is True
    assert report.battery_low_percent == 25
    assert report.battery_critical_percent == 10
    assert report.thermal_warning_c == 75
    assert report.thermal_critical_c == 85
    assert report.max_temp_c == 56


def test_build_report_fails_on_critical_conditions():
    report = build_report(
        [
            BurnInSample(
                ts=1,
                camera_ok=True,
                camera_error=None,
                battery_percent=9,
                battery_charging=False,
                battery_source="bat",
                temp_c=86,
                thermal_source="thermal",
                thermal_label="cpu",
                network_online=True,
                network_error=None,
            )
        ],
        started_at=1,
        ended_at=61,
        config=BoxConfig(battery_critical_percent=10, thermal_critical_c=85),
    )

    assert report.passed is False
    assert report.battery_critical_seen is True
    assert report.thermal_critical_seen is True


def test_runner_writes_samples_and_report(tmp_path: Path):
    clock = _FakeClock([0, 0, 61, 61])
    runner = BoxBurnInRunner(
        BoxConfig(),
        camera_probe=lambda _: CameraProbeResult(True, 0, width=640, height=480),
        power=_StaticPower(BatteryStatus(90, False, "bat")),
        thermal=_StaticThermal(ThermalStatus(44, "thermal", "cpu")),
        network=_StaticNetwork(NetworkStatus(True, "probe")),
        clock=clock,
        sleeper=lambda _: None,
    )

    report = runner.run(duration_seconds=0, interval_seconds=60, output_dir=tmp_path)

    assert report.passed is True
    assert (tmp_path / "samples.jsonl").exists()
    assert (tmp_path / "report.json").exists()
    saved = json.loads((tmp_path / "report.json").read_text())
    assert saved["passed"] is True
    assert saved["sample_count"] == 1
    assert saved["charging_seen"] is False


class _FakeClock:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def __call__(self) -> float:
        if self.values:
            return self.values.pop(0)
        return 61


class _StaticPower:
    def __init__(self, status: BatteryStatus) -> None:
        self.status = status

    def read(self) -> BatteryStatus:
        return self.status


class _StaticThermal:
    def __init__(self, status: ThermalStatus) -> None:
        self.status = status

    def read(self) -> ThermalStatus:
        return self.status


class _StaticNetwork:
    def __init__(self, status: NetworkStatus) -> None:
        self.status = status

    def check(self) -> NetworkStatus:
        return self.status
