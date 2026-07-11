"""Audit declaratif du hardware installe dans une Boring Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from boring.hardware_presets import load_hardware_presets

SUPPORTED_PI_MODELS = {"raspberry-pi-4", "raspberry-pi-5"}
SUPPORTED_CAMERA_TYPES = {"usb-uvc", "camera-module-3", "camera-module-3-wide"}


@dataclass(frozen=True)
class HardwareCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class HardwareProfileReport:
    path: str
    checks: list[HardwareCheck]

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def audit_hardware_profile(path: Path) -> HardwareProfileReport:
    if not path.exists():
        return HardwareProfileReport(
            str(path),
            [HardwareCheck("hardware_profile", False, f"missing {path}")],
        )
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return HardwareProfileReport(
            str(path),
            [HardwareCheck("hardware_profile", False, f"invalid json {path}")],
        )
    checks = [
        _check_pi(payload),
        _check_preset(payload),
        _check_camera(payload),
        _check_storage(payload),
        _check_power(payload),
        _check_network(payload),
    ]
    return HardwareProfileReport(str(path), checks)


def _check_pi(payload: dict) -> HardwareCheck:
    board = payload.get("board") or {}
    model = str(board.get("model") or "")
    ram_gb = _float(board.get("ram_gb"))
    min_ram = 8 if model == "raspberry-pi-5" else 4
    ok = model in SUPPORTED_PI_MODELS and ram_gb is not None and ram_gb >= min_ram
    return HardwareCheck(
        "pi_board",
        ok,
        f"model={model or 'missing'}, ram={ram_gb or 0:g}GB/{min_ram}GB",
    )


def _check_preset(payload: dict) -> HardwareCheck:
    preset_id = str(payload.get("preset_id") or "")
    if not preset_id:
        return HardwareCheck("hardware_preset", False, "missing preset_id")
    try:
        catalog = load_hardware_presets()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return HardwareCheck("hardware_preset", False, f"invalid preset catalog: {exc}")
    preset = catalog.by_id(preset_id)
    if preset is None:
        return HardwareCheck("hardware_preset", False, f"unknown preset_id={preset_id}")

    board = payload.get("board") or {}
    storage = payload.get("storage") or {}
    power = payload.get("power") or {}
    runtime = payload.get("runtime") or {}
    model = str(board.get("model") or "")
    ram_gb = _float(board.get("ram_gb")) or 0
    storage_gb = _float(storage.get("capacity_gb")) or 0
    battery_wh = _float(power.get("battery_capacity_wh")) or 0
    vehicle_charge_watts = _float(power.get("vehicle_charge_watts")) or 0
    detection_fps = _float(runtime.get("detection_fps")) or 0

    failures = []
    if model != preset.board_model:
        failures.append(f"model={model or 'missing'}/{preset.board_model}")
    if ram_gb < preset.min_ram_gb:
        failures.append(f"ram={ram_gb:g}GB/{preset.min_ram_gb:g}GB")
    if storage_gb < preset.min_storage_gb:
        failures.append(f"storage={storage_gb:g}GB/{preset.min_storage_gb:g}GB")
    if battery_wh < preset.min_battery_wh:
        failures.append(f"battery={battery_wh:g}Wh/{preset.min_battery_wh:g}Wh")
    if vehicle_charge_watts < preset.min_vehicle_charge_watts:
        failures.append(
            f"vehicle_charge={vehicle_charge_watts:g}W/{preset.min_vehicle_charge_watts:g}W"
        )
    if detection_fps < preset.recommended_detection_fps:
        failures.append(f"detection_fps={detection_fps:g}/{preset.recommended_detection_fps:g}")

    return HardwareCheck(
        "hardware_preset",
        not failures,
        f"preset={preset_id}" if not failures else f"preset={preset_id}, " + ", ".join(failures),
    )


def _check_camera(payload: dict) -> HardwareCheck:
    camera = payload.get("camera") or {}
    camera_type = str(camera.get("type") or "")
    device = str(camera.get("device") or "")
    ok = camera_type in SUPPORTED_CAMERA_TYPES and bool(device)
    return HardwareCheck(
        "camera",
        ok,
        f"type={camera_type or 'missing'}, device={device or 'missing'}",
    )


def _check_storage(payload: dict) -> HardwareCheck:
    storage = payload.get("storage") or {}
    capacity_gb = _float(storage.get("capacity_gb"))
    endurance = bool(storage.get("endurance"))
    ok = capacity_gb is not None and capacity_gb >= 64 and endurance
    return HardwareCheck(
        "storage",
        ok,
        f"capacity={capacity_gb or 0:g}GB/64GB, endurance={endurance}",
    )


def _check_power(payload: dict) -> HardwareCheck:
    power = payload.get("power") or {}
    battery_capacity_wh = _float(power.get("battery_capacity_wh"))
    vehicle_charge_watts = _float(power.get("vehicle_charge_watts"))
    ups_power_supply = bool(power.get("ups_power_supply"))
    ok = (
        battery_capacity_wh is not None
        and battery_capacity_wh >= 80
        and vehicle_charge_watts is not None
        and vehicle_charge_watts >= 30
        and ups_power_supply
    )
    return HardwareCheck(
        "power_hardware",
        ok,
        (
            f"battery={battery_capacity_wh or 0:g}Wh/80Wh, "
            f"vehicle_charge={vehicle_charge_watts or 0:g}W/30W, "
            f"ups_power_supply={ups_power_supply}"
        ),
    )


def _check_network(payload: dict) -> HardwareCheck:
    network = payload.get("network") or {}
    mode = str(network.get("mode") or "")
    ok = mode in {"wifi", "4g", "5g", "ethernet", "hotspot"}
    return HardwareCheck("network", ok, f"mode={mode or 'missing'}")


def _float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
