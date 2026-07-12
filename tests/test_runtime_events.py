from __future__ import annotations

from boring.runtime_events import BLOCKING_RUNTIME_EVENTS


def test_blocking_runtime_events_cover_field_readiness_failures():
    assert BLOCKING_RUNTIME_EVENTS == frozenset(
        {
            "battery_critical",
            "battery_sensor_missing",
            "disk_low",
            "network_offline",
            "notification_failed",
            "payment_skipped_battery_critical",
            "payment_skipped_no_position",
            "payment_skipped_offline",
            "service_crashed",
            "thermal_critical",
        }
    )
