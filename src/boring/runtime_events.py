"""Noms d'evenements runtime partages par les gates terrain."""

from __future__ import annotations

BLOCKING_RUNTIME_EVENTS = frozenset(
    {
        "battery_critical",
        "battery_sensor_missing",
        "disk_low",
        "network_offline",
        "notification_failed",
        "payment_skipped_battery_critical",
        "payment_skipped_no_position",
        "payment_skipped_offline",
        "payment_skipped_state_corrupt",
        "payment_state_persist_failed",
        "service_crashed",
        "thermal_critical",
    }
)
