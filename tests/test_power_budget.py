from __future__ import annotations

import pytest

from boring.power_budget import build_power_budget


def test_power_budget_passes_with_usable_capacity_and_vehicle_recharge():
    budget = build_power_budget(
        capacity_wh=100,
        draw_watts=8,
        required_runtime_hours=10,
        reserve_percent=15,
        vehicle_charge_watts=30,
        daily_drive_recharge_hours=1,
        charge_efficiency=0.85,
    )

    assert budget is not None
    assert budget.usable_capacity_wh == 85
    assert budget.parked_runtime_hours == 10.625
    assert budget.charge_surplus_watts == 22
    assert budget.daily_recovered_wh == pytest.approx(18.7)
    assert budget.passed is True


def test_power_budget_fails_when_capacity_only_passes_without_vehicle_recharge():
    budget = build_power_budget(
        capacity_wh=100,
        draw_watts=8,
        required_runtime_hours=10,
        reserve_percent=15,
        vehicle_charge_watts=None,
        daily_drive_recharge_hours=1,
    )

    assert budget is not None
    assert budget.parked_runtime_hours >= 10
    assert budget.has_vehicle_recharge is False
    assert budget.passed is False


def test_power_budget_fails_when_capacity_does_not_cover_required_day():
    budget = build_power_budget(
        capacity_wh=70,
        draw_watts=8,
        required_runtime_hours=10,
        reserve_percent=15,
        vehicle_charge_watts=30,
        daily_drive_recharge_hours=1,
    )

    assert budget is not None
    assert budget.parked_runtime_hours < 10
    assert budget.has_vehicle_recharge is True
    assert budget.passed is False
