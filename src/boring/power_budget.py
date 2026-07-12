"""Budget energie pour une box Raspberry Pi rechargeable en voiture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PowerBudget:
    capacity_wh: float
    draw_watts: float
    required_runtime_hours: float
    reserve_percent: float = 15.0
    vehicle_charge_watts: float | None = None
    daily_drive_recharge_hours: float = 0.0
    charge_efficiency: float = 0.85

    @property
    def usable_capacity_wh(self) -> float:
        reserve_ratio = min(max(self.reserve_percent, 0.0), 95.0) / 100
        return self.capacity_wh * (1 - reserve_ratio)

    @property
    def parked_runtime_hours(self) -> float:
        if self.draw_watts <= 0:
            return 0.0
        return self.usable_capacity_wh / self.draw_watts

    @property
    def charge_surplus_watts(self) -> float:
        if self.vehicle_charge_watts is None:
            return 0.0
        return max(0.0, self.vehicle_charge_watts - self.draw_watts)

    @property
    def daily_recovered_wh(self) -> float:
        return self.charge_surplus_watts * self.daily_drive_recharge_hours * self.charge_efficiency

    @property
    def required_runtime_energy_wh(self) -> float:
        return self.draw_watts * self.required_runtime_hours

    @property
    def daily_recharge_coverage_ratio(self) -> float:
        required = self.required_runtime_energy_wh
        if required <= 0:
            return 0.0
        return self.daily_recovered_wh / required

    @property
    def required_drive_recharge_hours(self) -> float | None:
        recovered_per_hour = self.charge_surplus_watts * self.charge_efficiency
        if recovered_per_hour <= 0:
            return None
        return self.required_runtime_energy_wh / recovered_per_hour

    @property
    def daily_supported_runtime_hours(self) -> float:
        if self.draw_watts <= 0:
            return 0.0
        return (self.usable_capacity_wh + self.daily_recovered_wh) / self.draw_watts

    @property
    def has_vehicle_recharge(self) -> bool:
        return (
            self.vehicle_charge_watts is not None
            and self.vehicle_charge_watts > self.draw_watts
            and self.daily_drive_recharge_hours > 0
            and self.charge_efficiency > 0
        )

    @property
    def passed(self) -> bool:
        return (
            self.parked_runtime_hours >= self.required_runtime_hours and self.has_vehicle_recharge
        )


def build_power_budget(
    *,
    capacity_wh: float | None,
    draw_watts: float,
    required_runtime_hours: float,
    reserve_percent: float = 15.0,
    vehicle_charge_watts: float | None = None,
    daily_drive_recharge_hours: float = 0.0,
    charge_efficiency: float = 0.85,
) -> PowerBudget | None:
    if capacity_wh is None or capacity_wh <= 0 or draw_watts <= 0 or required_runtime_hours <= 0:
        return None
    return PowerBudget(
        capacity_wh=capacity_wh,
        draw_watts=draw_watts,
        required_runtime_hours=required_runtime_hours,
        reserve_percent=reserve_percent,
        vehicle_charge_watts=vehicle_charge_watts,
        daily_drive_recharge_hours=max(0.0, daily_drive_recharge_hours),
        charge_efficiency=max(0.0, min(charge_efficiency, 1.0)),
    )
