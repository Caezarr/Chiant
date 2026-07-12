"""Configuration runtime pour la box Boring."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return float(value)


@dataclass(frozen=True)
class BoxConfig:
    """Parametres du service headless embarque."""

    camera_device: int = 0
    model_path: str = "yolov8n.pt"
    target_labels: tuple[str, ...] = ("car",)
    detection_device: str = "auto"
    confidence_threshold: float = 0.5
    inference_fps: float = 5.0
    low_power_inference_fps: float = 1.0
    consecutive_frames: int = 3
    default_duration_minutes: int = 15
    cooldown_minutes: int = 10
    max_session_amount_cents: int = 500
    max_daily_amount_cents: int = 1500
    vehicle_plate: str = "AA-000-AA"
    position_mode: str = "static"
    lat: float | None = None
    lon: float | None = None
    gpsd_host: str = "127.0.0.1"
    gpsd_port: int = 2947
    require_geofence: bool = True
    zones_path: Path = Path("data/lille_parking_zones.geojson")
    state_path: Path = Path("/var/lib/boring/state.json")
    event_log_path: Path = Path("/var/lib/boring/events.jsonl")
    event_log_max_bytes: int = 5_000_000
    event_log_backups: int = 3
    disk_min_free_mb: int = 512
    disk_check_seconds: int = 300
    payment_dry_run: bool = True
    battery_low_percent: int = 25
    battery_critical_percent: int = 10
    battery_recovered_percent: int = 35
    battery_capacity_wh: float | None = None
    estimated_draw_watts: float = 8.0
    required_runtime_hours: float = 10.0
    power_reserve_percent: float = 15.0
    vehicle_charge_watts: float | None = None
    daily_drive_recharge_hours: float = 1.0
    charge_efficiency: float = 0.85
    power_check_seconds: int = 60
    thermal_warning_c: float = 75.0
    thermal_critical_c: float = 85.0
    thermal_check_seconds: int = 60
    network_check_seconds: int = 60
    network_probe_target: str = "1.1.1.1:443"
    network_recovery_command: str | None = None
    network_recovery_cooldown_seconds: int = 300
    network_recovery_timeout_seconds: float = 20.0
    heartbeat_seconds: int = 900
    notify_webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> "BoxConfig":
        labels = tuple(
            label.strip()
            for label in os.getenv("DETECTION_TARGET_LABELS", "car").split(",")
            if label.strip()
        )
        return cls(
            camera_device=int(os.getenv("CAMERA_DEVICE", "0")),
            model_path=os.getenv("DETECTION_MODEL", "yolov8n.pt"),
            target_labels=labels or ("car",),
            detection_device=os.getenv("DETECTION_DEVICE", "auto"),
            confidence_threshold=float(os.getenv("DETECTION_CONFIDENCE_THRESHOLD", "0.5")),
            inference_fps=float(os.getenv("DETECTION_FPS", "5.0")),
            low_power_inference_fps=float(os.getenv("LOW_POWER_DETECTION_FPS", "1.0")),
            consecutive_frames=int(os.getenv("DETECTION_CONSECUTIVE_FRAMES", "3")),
            default_duration_minutes=int(os.getenv("DEFAULT_DURATION_MINUTES", "15")),
            cooldown_minutes=int(os.getenv("COOLDOWN_MINUTES", "10")),
            max_session_amount_cents=int(os.getenv("MAX_SESSION_AMOUNT_CENTS", "500")),
            max_daily_amount_cents=int(os.getenv("MAX_DAILY_AMOUNT_CENTS", "1500")),
            vehicle_plate=os.getenv("DEFAULT_VEHICLE_PLATE", "AA-000-AA"),
            position_mode=os.getenv("POSITION_MODE", "static"),
            lat=env_float("BOX_LAT"),
            lon=env_float("BOX_LON"),
            gpsd_host=os.getenv("GPSD_HOST", "127.0.0.1"),
            gpsd_port=int(os.getenv("GPSD_PORT", "2947")),
            require_geofence=env_bool("BOX_REQUIRE_GEOFENCE", True),
            zones_path=Path(os.getenv("PARKING_ZONES_PATH", "data/lille_parking_zones.geojson")),
            state_path=Path(os.getenv("BOX_STATE_PATH", "/var/lib/boring/state.json")),
            event_log_path=Path(os.getenv("BOX_EVENT_LOG_PATH", "/var/lib/boring/events.jsonl")),
            event_log_max_bytes=int(os.getenv("BOX_EVENT_LOG_MAX_BYTES", "5000000")),
            event_log_backups=int(os.getenv("BOX_EVENT_LOG_BACKUPS", "3")),
            disk_min_free_mb=int(os.getenv("BOX_DISK_MIN_FREE_MB", "512")),
            disk_check_seconds=int(os.getenv("BOX_DISK_CHECK_SECONDS", "300")),
            payment_dry_run=env_bool("PAYMENT_DRY_RUN", True),
            battery_low_percent=int(os.getenv("BATTERY_LOW_PERCENT", "25")),
            battery_critical_percent=int(os.getenv("BATTERY_CRITICAL_PERCENT", "10")),
            battery_recovered_percent=int(os.getenv("BATTERY_RECOVERED_PERCENT", "35")),
            battery_capacity_wh=env_float("BATTERY_CAPACITY_WH"),
            estimated_draw_watts=float(os.getenv("ESTIMATED_DRAW_WATTS", "8.0")),
            required_runtime_hours=float(os.getenv("REQUIRED_RUNTIME_HOURS", "10.0")),
            power_reserve_percent=float(os.getenv("POWER_RESERVE_PERCENT", "15.0")),
            vehicle_charge_watts=env_float("VEHICLE_CHARGE_WATTS"),
            daily_drive_recharge_hours=float(os.getenv("DAILY_DRIVE_RECHARGE_HOURS", "1.0")),
            charge_efficiency=float(os.getenv("CHARGE_EFFICIENCY", "0.85")),
            power_check_seconds=int(os.getenv("POWER_CHECK_SECONDS", "60")),
            thermal_warning_c=float(os.getenv("THERMAL_WARNING_C", "75.0")),
            thermal_critical_c=float(os.getenv("THERMAL_CRITICAL_C", "85.0")),
            thermal_check_seconds=int(os.getenv("THERMAL_CHECK_SECONDS", "60")),
            network_check_seconds=int(os.getenv("NETWORK_CHECK_SECONDS", "60")),
            network_probe_target=os.getenv("NETWORK_PROBE_TARGET", "1.1.1.1:443"),
            network_recovery_command=os.getenv("NETWORK_RECOVERY_COMMAND") or None,
            network_recovery_cooldown_seconds=int(
                os.getenv("NETWORK_RECOVERY_COOLDOWN_SECONDS", "300")
            ),
            network_recovery_timeout_seconds=float(
                os.getenv("NETWORK_RECOVERY_TIMEOUT_SECONDS", "20.0")
            ),
            heartbeat_seconds=int(os.getenv("BOX_HEARTBEAT_SECONDS", "900")),
            notify_webhook_url=os.getenv("BORING_NOTIFY_WEBHOOK_URL") or None,
        )
