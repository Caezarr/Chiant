from __future__ import annotations

from boring.config import BoxConfig, env_bool


def test_env_bool_defaults(monkeypatch):
    monkeypatch.delenv("BORING_TEST_BOOL", raising=False)
    assert env_bool("BORING_TEST_BOOL", True) is True
    assert env_bool("BORING_TEST_BOOL", False) is False


def test_box_config_from_env(monkeypatch):
    monkeypatch.setenv("CAMERA_DEVICE", "2")
    monkeypatch.setenv("DETECTION_TARGET_LABELS", "control_vehicle,police_car")
    monkeypatch.setenv("DETECTION_MODEL", "models/best.pt")
    monkeypatch.setenv("DETECTION_DEVICE", "cpu")
    monkeypatch.setenv("LOW_POWER_DETECTION_FPS", "0.5")
    monkeypatch.setenv("PAYMENT_DRY_RUN", "false")
    monkeypatch.setenv("MAX_SESSION_AMOUNT_CENTS", "400")
    monkeypatch.setenv("MAX_DAILY_AMOUNT_CENTS", "1200")
    monkeypatch.setenv("BOX_STATE_PATH", "/tmp/boring-state.json")
    monkeypatch.setenv("BOX_EVENT_LOG_MAX_BYTES", "12345")
    monkeypatch.setenv("BOX_EVENT_LOG_BACKUPS", "7")
    monkeypatch.setenv("BOX_DISK_MIN_FREE_MB", "256")
    monkeypatch.setenv("BOX_DISK_CHECK_SECONDS", "45")
    monkeypatch.setenv("POSITION_MODE", "gpsd")
    monkeypatch.setenv("GPSD_HOST", "gps.local")
    monkeypatch.setenv("GPSD_PORT", "2948")
    monkeypatch.setenv("BATTERY_RECOVERED_PERCENT", "40")
    monkeypatch.setenv("BATTERY_CAPACITY_WH", "100")
    monkeypatch.setenv("ESTIMATED_DRAW_WATTS", "8")
    monkeypatch.setenv("POWER_RESERVE_PERCENT", "20")
    monkeypatch.setenv("VEHICLE_CHARGE_WATTS", "30")
    monkeypatch.setenv("DAILY_DRIVE_RECHARGE_HOURS", "1.5")
    monkeypatch.setenv("CHARGE_EFFICIENCY", "0.8")
    monkeypatch.setenv("THERMAL_WARNING_C", "70")
    monkeypatch.setenv("THERMAL_CRITICAL_C", "82")
    monkeypatch.setenv("THERMAL_CHECK_SECONDS", "30")
    monkeypatch.setenv("NETWORK_PROBE_TARGET", "example.com:443")
    monkeypatch.setenv("NETWORK_PROBE_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("BOX_LAT", "50.6371")
    monkeypatch.setenv("BOX_LON", "3.0633")
    monkeypatch.setenv("BORING_NOTIFY_WEBHOOK_URL", "https://notify.example.test/boring")

    config = BoxConfig.from_env()

    assert config.camera_device == 2
    assert config.target_labels == ("control_vehicle", "police_car")
    assert config.model_path == "models/best.pt"
    assert config.detection_device == "cpu"
    assert config.low_power_inference_fps == 0.5
    assert config.payment_dry_run is False
    assert config.max_session_amount_cents == 400
    assert config.max_daily_amount_cents == 1200
    assert str(config.state_path) == "/tmp/boring-state.json"
    assert config.event_log_max_bytes == 12345
    assert config.event_log_backups == 7
    assert config.disk_min_free_mb == 256
    assert config.disk_check_seconds == 45
    assert config.position_mode == "gpsd"
    assert config.gpsd_host == "gps.local"
    assert config.gpsd_port == 2948
    assert config.battery_recovered_percent == 40
    assert config.battery_capacity_wh == 100
    assert config.estimated_draw_watts == 8
    assert config.power_reserve_percent == 20
    assert config.vehicle_charge_watts == 30
    assert config.daily_drive_recharge_hours == 1.5
    assert config.charge_efficiency == 0.8
    assert config.thermal_warning_c == 70
    assert config.thermal_critical_c == 82
    assert config.thermal_check_seconds == 30
    assert config.network_probe_target == "example.com:443"
    assert config.network_probe_timeout_seconds == 4.5
    assert config.lat == 50.6371
    assert config.lon == 3.0633
    assert config.notify_webhook_url == "https://notify.example.test/boring"


def test_box_config_reports_runtime_invariants():
    config = BoxConfig(
        inference_fps=1.0,
        low_power_inference_fps=2.0,
        battery_low_percent=25,
        battery_critical_percent=30,
        battery_recovered_percent=20,
        thermal_warning_c=90,
        thermal_critical_c=85,
        max_session_amount_cents=500,
        max_daily_amount_cents=400,
        heartbeat_seconds=0,
    )

    failures = config.validation_failures()

    assert "LOW_POWER_DETECTION_FPS=2.0>1.0" in failures
    assert "battery_thresholds=30/25" in failures
    assert "BATTERY_RECOVERED_PERCENT=20<=25" in failures
    assert "thermal_thresholds=90/85" in failures
    assert "MAX_DAILY_AMOUNT_CENTS=400<500" in failures
    assert "BOX_HEARTBEAT_SECONDS=0" in failures


def test_box_config_accepts_runtime_invariants():
    config = BoxConfig()

    assert config.validation_failures() == []
