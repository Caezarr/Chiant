from __future__ import annotations

from pathlib import Path

from boring.power import LinuxPowerSupplyMonitor, LinuxThermalMonitor, estimate_runtime_hours


def test_linux_power_supply_monitor_reads_battery(tmp_path: Path):
    supply = tmp_path / "BAT0"
    supply.mkdir()
    (supply / "capacity").write_text("18\n")
    (supply / "status").write_text("Discharging\n")

    status = LinuxPowerSupplyMonitor(tmp_path).read()

    assert status is not None
    assert status.percent == 18
    assert status.charging is False
    assert status.source == str(supply)


def test_linux_power_supply_monitor_missing_root(tmp_path: Path):
    status = LinuxPowerSupplyMonitor(tmp_path / "missing").read()

    assert status is None


def test_linux_thermal_monitor_reads_hottest_zone(tmp_path: Path):
    zone0 = tmp_path / "thermal_zone0"
    zone0.mkdir()
    (zone0 / "temp").write_text("48000\n")
    (zone0 / "type").write_text("cpu-thermal\n")
    zone1 = tmp_path / "thermal_zone1"
    zone1.mkdir()
    (zone1 / "temp").write_text("71500\n")
    (zone1 / "type").write_text("pmic\n")

    status = LinuxThermalMonitor(tmp_path).read()

    assert status is not None
    assert status.temp_c == 71.5
    assert status.source == str(zone1)
    assert status.label == "pmic"


def test_linux_thermal_monitor_missing_root(tmp_path: Path):
    status = LinuxThermalMonitor(tmp_path / "missing").read()

    assert status is None


def test_estimate_runtime_hours():
    assert estimate_runtime_hours(100, 8) == 12.5
    assert estimate_runtime_hours(None, 8) is None
    assert estimate_runtime_hours(100, 0) is None
