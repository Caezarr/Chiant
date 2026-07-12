"""Presets materiels supportes pour la Boring Parking Box."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwarePreset:
    id: str
    label: str
    board_model: str
    min_ram_gb: float
    min_storage_gb: float
    min_battery_wh: float
    min_vehicle_charge_watts: float
    recommended_detection_fps: float
    min_benchmark_fps: float
    thermal_margin: str


@dataclass(frozen=True)
class HardwarePresetCatalog:
    version: int
    updated_at: str
    presets: list[HardwarePreset]

    def by_id(self, preset_id: str) -> HardwarePreset | None:
        return next((preset for preset in self.presets if preset.id == preset_id), None)


def load_hardware_presets(path: Path = Path("data/hardware_presets.json")) -> HardwarePresetCatalog:
    payload = json.loads(path.read_text())
    presets = [
        HardwarePreset(
            id=str(item["id"]),
            label=str(item["label"]),
            board_model=str(item["board_model"]),
            min_ram_gb=float(item["min_ram_gb"]),
            min_storage_gb=float(item["min_storage_gb"]),
            min_battery_wh=float(item["min_battery_wh"]),
            min_vehicle_charge_watts=float(item["min_vehicle_charge_watts"]),
            recommended_detection_fps=float(item["recommended_detection_fps"]),
            min_benchmark_fps=float(item["min_benchmark_fps"]),
            thermal_margin=str(item["thermal_margin"]),
        )
        for item in payload.get("presets", [])
    ]
    return HardwarePresetCatalog(
        version=int(payload.get("version", 0)),
        updated_at=str(payload.get("updated_at", "")),
        presets=presets,
    )
