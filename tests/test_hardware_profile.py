from __future__ import annotations

import json
from pathlib import Path

from boring.hardware_profile import audit_hardware_profile


def test_hardware_profile_passes_with_pi5_box(tmp_path: Path):
    profile = _write_profile(tmp_path)

    report = audit_hardware_profile(profile)

    assert report.passed is True
    assert all(check.ok for check in report.checks)


def test_hardware_profile_fails_when_missing(tmp_path: Path):
    report = audit_hardware_profile(tmp_path / "missing.json")

    assert report.passed is False
    assert report.checks[0].name == "hardware_profile"


def test_hardware_profile_fails_when_power_is_too_weak(tmp_path: Path):
    profile = _write_profile(tmp_path, battery_capacity_wh=50, vehicle_charge_watts=10)

    report = audit_hardware_profile(profile)

    assert report.passed is False
    assert any(check.name == "power_hardware" and not check.ok for check in report.checks)


def test_hardware_profile_fails_when_preset_requirements_are_not_met(tmp_path: Path):
    profile = _write_profile(tmp_path, battery_capacity_wh=80)

    report = audit_hardware_profile(profile)

    assert report.passed is False
    preset = [check for check in report.checks if check.name == "hardware_preset"][0]
    assert "battery=80Wh/100Wh" in preset.detail


def _write_profile(
    tmp_path: Path,
    *,
    battery_capacity_wh: float = 100,
    vehicle_charge_watts: float = 30,
) -> Path:
    profile = tmp_path / "hardware-profile.json"
    profile.write_text(
        json.dumps(
            {
                "board": {"model": "raspberry-pi-5", "ram_gb": 8},
                "preset_id": "pi5-production",
                "camera": {"type": "usb-uvc", "device": "/dev/video0"},
                "storage": {"capacity_gb": 64, "endurance": True},
                "power": {
                    "ups_power_supply": True,
                    "battery_capacity_wh": battery_capacity_wh,
                    "vehicle_charge_watts": vehicle_charge_watts,
                },
                "network": {"mode": "hotspot"},
                "runtime": {"detection_fps": 2.0},
            }
        )
    )
    return profile
