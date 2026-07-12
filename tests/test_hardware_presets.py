from __future__ import annotations

import json
from pathlib import Path

from boring.hardware_presets import load_hardware_presets


def test_load_hardware_presets_finds_pi5_production(tmp_path: Path):
    path = tmp_path / "hardware_presets.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-07-11",
                "presets": [
                    {
                        "id": "pi5-production",
                        "label": "Pi 5",
                        "board_model": "raspberry-pi-5",
                        "min_ram_gb": 8,
                        "min_storage_gb": 64,
                        "min_battery_wh": 100,
                        "min_vehicle_charge_watts": 30,
                        "recommended_detection_fps": 2.0,
                        "min_benchmark_fps": 2.0,
                        "thermal_margin": "field beta",
                    }
                ],
            }
        )
    )

    catalog = load_hardware_presets(path)

    preset = catalog.by_id("pi5-production")
    assert preset is not None
    assert preset.board_model == "raspberry-pi-5"
    assert preset.min_battery_wh == 100
