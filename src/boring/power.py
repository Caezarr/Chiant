"""Lecture batterie/UPS pour un boitier Linux headless."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BatteryStatus:
    percent: int | None
    charging: bool | None
    source: str

    @property
    def is_known(self) -> bool:
        return self.percent is not None


@dataclass(frozen=True)
class ThermalStatus:
    temp_c: float
    source: str
    label: str | None = None


class LinuxPowerSupplyMonitor:
    """Lit /sys/class/power_supply, expose par beaucoup de UPS HAT Raspberry Pi."""

    def __init__(self, root: Path = Path("/sys/class/power_supply")) -> None:
        self.root = root

    def read(self) -> BatteryStatus | None:
        if not self.root.exists():
            return None
        for supply in sorted(self.root.iterdir()):
            capacity_path = supply / "capacity"
            status_path = supply / "status"
            if not capacity_path.exists():
                continue
            percent = _read_int(capacity_path)
            status_text = _read_text(status_path)
            charging = None
            if status_text:
                charging = status_text.lower() in {"charging", "full"}
            return BatteryStatus(percent=percent, charging=charging, source=str(supply))
        return None


class LinuxThermalMonitor:
    """Lit /sys/class/thermal, expose par Linux sur Raspberry Pi."""

    def __init__(self, root: Path = Path("/sys/class/thermal")) -> None:
        self.root = root

    def read(self) -> ThermalStatus | None:
        if not self.root.exists():
            return None
        hottest: ThermalStatus | None = None
        for zone in sorted(self.root.glob("thermal_zone*")):
            temp_path = zone / "temp"
            if not temp_path.exists():
                continue
            millidegrees = _read_int(temp_path)
            if millidegrees is None:
                continue
            status = ThermalStatus(
                temp_c=millidegrees / 1000,
                source=str(zone),
                label=_read_text(zone / "type"),
            )
            if hottest is None or status.temp_c > hottest.temp_c:
                hottest = status
        return hottest


def estimate_runtime_hours(capacity_wh: float | None, draw_watts: float) -> float | None:
    """Retourne l'autonomie theorique en heures."""
    if capacity_wh is None or capacity_wh <= 0 or draw_watts <= 0:
        return None
    return capacity_wh / draw_watts


def estimate_available_capacity_wh(
    capacity_wh: float | None,
    battery_percent: int | None,
) -> float | None:
    """Retourne l'energie disponible au pourcentage batterie courant."""
    if capacity_wh is None or capacity_wh <= 0:
        return None
    if battery_percent is None or not 0 <= battery_percent <= 100:
        return None
    return capacity_wh * (battery_percent / 100)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _read_int(path: Path) -> int | None:
    value = _read_text(path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
