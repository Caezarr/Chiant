"""Gate final de readiness pour installer une box dans une voiture."""

from __future__ import annotations

import configparser
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from boring.autopay_readiness import audit_autopay_readiness
from boring.config import BoxConfig
from boring.hardware_profile import audit_hardware_profile
from boring.power_budget import build_power_budget
from boring.runtime_events import BLOCKING_RUNTIME_EVENTS
from boring.storage import DiskSpaceMonitor
from boring.vision_readiness import audit_vision_readiness


@dataclass(frozen=True)
class ProductionCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ProductionReadinessReport:
    checks: list[ProductionCheck]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def audit_production_readiness(
    *,
    env: Mapping[str, str] | None = None,
    dataset_path: Path = Path("datasets/control_vehicle_v1"),
    model_path: Path = Path("models/best.pt"),
    baseline_manifest: Path = Path("datasets/baseline/manifest.jsonl"),
    endpoints_path: Path = Path("scripts/paybyphone_endpoints.json"),
    hardware_profile_path: Path = Path("deploy/pi/hardware-profile.json"),
    service_unit_path: Path = Path("deploy/systemd/boring-box.service"),
    systemd_report_path: Path = Path("reports/systemd-check.json"),
    position_report_path: Path = Path("reports/position-check.json"),
    camera_report_path: Path = Path("reports/camera-check.json"),
    network_report_path: Path = Path("reports/network-check.json"),
    power_report_path: Path = Path("reports/power-check.json"),
    vision_eval_report_path: Path = Path("reports/vision-eval.json"),
    benchmark_report_path: Path = Path("reports/vision-benchmark.json"),
    autopay_smoke_report_path: Path = Path("reports/autopay-smoke.json"),
    notification_report_path: Path = Path("reports/notification-test.json"),
    burn_in_report_path: Path = Path("burn-in/report.json"),
    state_path: Path = Path("/var/lib/boring/state.json"),
    storage_path: Path = Path("/var/lib/boring/events.jsonl"),
    require_edge_export: bool = True,
    require_real_payment: bool = True,
    require_autopay_smoke: bool = True,
    require_charging_seen: bool = True,
    require_network_recovery: bool = True,
    require_notification_webhook: bool = True,
    require_notification_test: bool = True,
    require_runtime_event_log: bool = True,
    require_systemd_report: bool = True,
    require_position_report: bool = True,
    require_camera_report: bool = True,
    require_network_report: bool = True,
    require_power_report: bool = True,
    min_burn_in_hours: float = 10.0,
    now: datetime | None = None,
) -> ProductionReadinessReport:
    values = env or os.environ
    checked_at = now or datetime.now(timezone.utc)
    vision = audit_vision_readiness(
        dataset_path=dataset_path,
        model_path=model_path,
        baseline_manifest=baseline_manifest,
        require_edge_export=require_edge_export,
    )
    autopay = audit_autopay_readiness(
        env=values,
        endpoints_path=endpoints_path,
        require_real_payment=require_real_payment,
    )
    hardware = audit_hardware_profile(hardware_profile_path)
    checks = [
        _check_runtime_config(values),
        _summary_check("vision", vision.passed, _failed_names(vision.checks)),
        _summary_check("autopay", autopay.passed, _failed_names(autopay.checks)),
        _check_autopay_smoke_report(
            autopay_smoke_report_path,
            env=values,
            require_autopay_smoke=require_autopay_smoke,
        ),
        _summary_check("hardware", hardware.passed, _failed_names(hardware.checks)),
        _check_hardware_env_consistency(values, hardware_profile_path),
        _check_systemd_service(
            service_unit_path,
            state_path=state_path,
        ),
        _check_systemd_report(
            systemd_report_path,
            require_systemd_report=require_systemd_report,
        ),
        _check_position_report(
            position_report_path,
            values,
            require_position_report=require_position_report,
        ),
        _check_camera_report(
            camera_report_path,
            values,
            hardware_profile_path=hardware_profile_path,
            require_camera_report=require_camera_report,
        ),
        _check_network_report(
            network_report_path,
            values,
            require_network_report=require_network_report,
            require_network_recovery=require_network_recovery,
        ),
        _check_power_report(
            power_report_path,
            values,
            require_power_report=require_power_report,
        ),
        _check_vision_eval_report(
            vision_eval_report_path,
            expected_model_path=model_path,
            expected_dataset_path=dataset_path,
        ),
        _check_benchmark_report(
            benchmark_report_path,
            required_min_fps=_hardware_required_benchmark_fps(hardware_profile_path),
            expected_model_path=model_path,
        ),
        _check_power_budget(values),
        _check_network_recovery(values, require_network_recovery=require_network_recovery),
        _check_notification_webhook(
            values,
            require_notification_webhook=require_notification_webhook,
        ),
        _check_notification_report(
            notification_report_path,
            expected_webhook_host=_notification_webhook_host(values),
            expected_webhook_hash=_notification_webhook_hash(values),
            require_notification_test=require_notification_test,
        ),
        _check_state_path(values, state_path),
        _check_disk_space(values, storage_path),
        _check_burn_in_report(
            values,
            burn_in_report_path,
            min_burn_in_hours=min_burn_in_hours,
            require_charging_seen=require_charging_seen,
        ),
        _check_burn_in_samples(burn_in_report_path),
        _check_runtime_event_log(
            values,
            storage_path,
            burn_in_report_path,
            require_runtime_event_log=require_runtime_event_log,
            max_heartbeat_gap_seconds=_env_float(
                values,
                "BOX_READY_MAX_HEARTBEAT_GAP_SECONDS",
            )
            or 1800.0,
        ),
        _check_report_freshness(
            values,
            now=checked_at,
            systemd_report_path=systemd_report_path,
            position_report_path=position_report_path,
            camera_report_path=camera_report_path,
            network_report_path=network_report_path,
            power_report_path=power_report_path,
            vision_eval_report_path=vision_eval_report_path,
            benchmark_report_path=benchmark_report_path,
            autopay_smoke_report_path=autopay_smoke_report_path,
            notification_report_path=notification_report_path,
            burn_in_report_path=burn_in_report_path,
            require_systemd_report=require_systemd_report,
            require_position_report=require_position_report,
            require_camera_report=require_camera_report,
            require_network_report=require_network_report,
            require_power_report=require_power_report,
            require_autopay_smoke=require_autopay_smoke,
            require_notification_test=require_notification_test,
        ),
    ]
    return ProductionReadinessReport(checks, generated_at=checked_at.isoformat())


def write_report(report: ProductionReadinessReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _summary_check(name: str, ok: bool, failures: str) -> ProductionCheck:
    return ProductionCheck(name, ok, "ok" if ok else f"failed: {failures}")


def _failed_names(checks) -> str:
    names = [check.name for check in checks if not check.ok]
    return ", ".join(names) if names else "none"


def _check_runtime_config(env: Mapping[str, str]) -> ProductionCheck:
    previous: dict[str, str | None] = {}
    names = {
        "DETECTION_CONFIDENCE_THRESHOLD",
        "DETECTION_FPS",
        "LOW_POWER_DETECTION_FPS",
        "DETECTION_CONSECUTIVE_FRAMES",
        "DEFAULT_DURATION_MINUTES",
        "COOLDOWN_MINUTES",
        "MAX_SESSION_AMOUNT_CENTS",
        "MAX_DAILY_AMOUNT_CENTS",
        "BATTERY_LOW_PERCENT",
        "BATTERY_CRITICAL_PERCENT",
        "BATTERY_RECOVERED_PERCENT",
        "ESTIMATED_DRAW_WATTS",
        "REQUIRED_RUNTIME_HOURS",
        "POWER_CHECK_SECONDS",
        "THERMAL_WARNING_C",
        "THERMAL_CRITICAL_C",
        "THERMAL_CHECK_SECONDS",
        "NETWORK_CHECK_SECONDS",
        "BOX_HEARTBEAT_SECONDS",
    }
    for name in names:
        previous[name] = os.environ.get(name)
        value = env.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    try:
        failures = BoxConfig.from_env().validation_failures()
    except ValueError as exc:
        failures = [str(exc)]
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return ProductionCheck(
        "runtime_config",
        not failures,
        "ok" if not failures else ", ".join(failures),
    )


def _check_power_budget(env: Mapping[str, str]) -> ProductionCheck:
    capacity_wh = _env_float(env, "BATTERY_CAPACITY_WH")
    draw_watts = _env_float(env, "ESTIMATED_DRAW_WATTS") or 8.0
    required_hours = _env_float(env, "REQUIRED_RUNTIME_HOURS") or 10.0
    reserve_percent = _env_float(env, "POWER_RESERVE_PERCENT") or 15.0
    vehicle_charge_watts = _env_float(env, "VEHICLE_CHARGE_WATTS")
    daily_drive_recharge_hours = _env_float(env, "DAILY_DRIVE_RECHARGE_HOURS") or 0.0
    charge_efficiency = _env_float(env, "CHARGE_EFFICIENCY") or 0.85
    budget = build_power_budget(
        capacity_wh=capacity_wh,
        draw_watts=draw_watts,
        required_runtime_hours=required_hours,
        reserve_percent=reserve_percent,
        vehicle_charge_watts=vehicle_charge_watts,
        daily_drive_recharge_hours=daily_drive_recharge_hours,
        charge_efficiency=charge_efficiency,
    )
    if budget is None:
        return ProductionCheck("power_budget", False, "missing or invalid battery/draw/runtime")
    return ProductionCheck(
        "power_budget",
        budget.passed,
        (
            f"parked={budget.parked_runtime_hours:.1f}h/{required_hours:.1f}h, "
            f"usable={budget.usable_capacity_wh:.1f}Wh/{capacity_wh:.1f}Wh, "
            f"reserve={reserve_percent:.0f}%, charge={vehicle_charge_watts or 0:.1f}W, "
            f"surplus={budget.charge_surplus_watts:.1f}W, "
            f"daily_recovered={budget.daily_recovered_wh:.1f}Wh, "
            f"daily_supported={budget.daily_supported_runtime_hours:.1f}h, "
            f"required_recharge={_format_hours(budget.required_drive_recharge_hours)}, "
            f"daily_recharge_coverage={budget.daily_recharge_coverage_ratio:.0%}"
        ),
    )


def _check_hardware_env_consistency(env: Mapping[str, str], path: Path) -> ProductionCheck:
    if not path.exists():
        return ProductionCheck("hardware_env_consistency", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("hardware_env_consistency", False, f"invalid json {path}")
    power = payload.get("power") or {}
    profile_battery_wh = _json_float(power.get("battery_capacity_wh"))
    profile_charge_watts = _json_float(power.get("vehicle_charge_watts"))
    env_battery_wh = _env_float(env, "BATTERY_CAPACITY_WH")
    env_charge_watts = _env_float(env, "VEHICLE_CHARGE_WATTS")
    missing = []
    if profile_battery_wh is None:
        missing.append("profile.power.battery_capacity_wh")
    if profile_charge_watts is None:
        missing.append("profile.power.vehicle_charge_watts")
    if env_battery_wh is None:
        missing.append("BATTERY_CAPACITY_WH")
    if env_charge_watts is None:
        missing.append("VEHICLE_CHARGE_WATTS")
    if missing:
        return ProductionCheck("hardware_env_consistency", False, f"missing {', '.join(missing)}")

    battery_ok = abs(profile_battery_wh - env_battery_wh) <= 1.0
    charge_ok = abs(profile_charge_watts - env_charge_watts) <= 1.0
    return ProductionCheck(
        "hardware_env_consistency",
        battery_ok and charge_ok,
        (
            f"battery profile/env={profile_battery_wh:.1f}/{env_battery_wh:.1f}Wh, "
            f"charge profile/env={profile_charge_watts:.1f}/{env_charge_watts:.1f}W"
        ),
    )


def _check_systemd_service(path: Path, *, state_path: Path) -> ProductionCheck:
    if not path.exists():
        return ProductionCheck("systemd_service", False, f"missing {path}")
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str.lower
    try:
        parser.read_string(path.read_text())
    except (OSError, configparser.Error) as exc:
        return ProductionCheck("systemd_service", False, f"invalid {path}: {exc}")

    service = parser["Service"] if parser.has_section("Service") else {}
    install = parser["Install"] if parser.has_section("Install") else {}
    service_type = str(service.get("type", "")).strip().lower()
    exec_start = str(service.get("execstart", ""))
    working_directory = str(service.get("workingdirectory", "")).strip()
    environment_file = str(service.get("environmentfile", "")).strip()
    restart = str(service.get("restart", "")).strip().lower()
    watchdog = _duration_seconds(str(service.get("watchdogsec", "")))
    notify_access = str(service.get("notifyaccess", "")).strip().lower()
    user = str(service.get("user", "")).strip()
    supplementary = set(str(service.get("supplementarygroups", "")).split())
    read_write_paths = set(str(service.get("readwritepaths", "")).split())
    wanted_by = str(install.get("wantedby", "")).strip()

    failures = []
    if service_type != "notify":
        failures.append(f"Type={service_type or '-'}")
    if "boring box-run" not in exec_start:
        failures.append("ExecStart")
    if not working_directory:
        failures.append("WorkingDirectory")
    if not environment_file:
        failures.append("EnvironmentFile")
    elif working_directory and environment_file != f"{working_directory}/.env":
        failures.append(f"EnvironmentFile={environment_file}")
    if restart != "always":
        failures.append(f"Restart={restart or '-'}")
    if watchdog is None or watchdog <= 0:
        failures.append(f"WatchdogSec={service.get('watchdogsec', '-')}")
    if notify_access not in {"main", "all"}:
        failures.append(f"NotifyAccess={notify_access or '-'}")
    if user != "boring":
        failures.append(f"User={user or '-'}")
    missing_groups = {"video", "gpio", "i2c", "netdev"} - supplementary
    if missing_groups:
        failures.append(f"groups={','.join(sorted(missing_groups))}")
    expected_write_paths = {
        working_directory,
        str(state_path.parent),
    } - {""}
    missing_paths = expected_write_paths - read_write_paths
    if missing_paths:
        failures.append(f"write_paths={','.join(sorted(missing_paths))}")
    if wanted_by != "multi-user.target":
        failures.append(f"WantedBy={wanted_by or '-'}")

    return ProductionCheck(
        "systemd_service",
        not failures,
        (
            f"type={service_type or '-'}, watchdog={watchdog or 0:.0f}s, "
            f"restart={restart or '-'}, user={user or '-'}, "
            f"workdir={working_directory or '-'}, "
            f"failures={', '.join(failures) if failures else '-'}"
        ),
    )


def _check_systemd_report(path: Path, *, require_systemd_report: bool) -> ProductionCheck:
    if not require_systemd_report:
        return ProductionCheck(
            "systemd_runtime",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("systemd_runtime", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("systemd_runtime", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    service = str(payload.get("service") or "")
    enabled = str(payload.get("enabled_state") or "")
    active = str(payload.get("active_state") or "")
    sub = str(payload.get("sub_state") or "")
    unit_file = str(payload.get("unit_file_state") or "")
    service_type = str(payload.get("type") or "")
    watchdog_usec = _json_float(payload.get("watchdog_usec")) or 0
    main_pid = _json_int(payload.get("main_pid")) or 0
    n_restarts = _json_int(payload.get("n_restarts"))
    exec_start = str(payload.get("exec_start") or "")
    user = str(payload.get("user") or "")
    failures = payload.get("failures")
    failures_text = (
        ",".join(str(failure) for failure in failures) if isinstance(failures, list) else "-"
    )
    ok = (
        passed
        and service == "boring-box.service"
        and enabled == "enabled"
        and active == "active"
        and sub == "running"
        and unit_file == "enabled"
        and service_type == "notify"
        and watchdog_usec > 0
        and main_pid > 0
        and n_restarts == 0
        and "boring box-run" in exec_start
        and user == "boring"
    )
    return ProductionCheck(
        "systemd_runtime",
        ok,
        (
            f"passed={passed}, service={service or '-'}, enabled={enabled or '-'}, "
            f"active={active or '-'}, sub={sub or '-'}, unit_file={unit_file or '-'}, "
            f"type={service_type or '-'}, watchdog_usec={watchdog_usec}, "
            f"main_pid={main_pid}, n_restarts={n_restarts if n_restarts is not None else '-'}, "
            f"user={user or '-'}, failures={failures_text}"
        ),
    )


def _check_position_report(
    path: Path,
    env: Mapping[str, str],
    *,
    require_position_report: bool,
) -> ProductionCheck:
    if not require_position_report:
        return ProductionCheck(
            "position_runtime",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("position_runtime", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("position_runtime", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    mode = str(payload.get("mode") or "")
    expected_mode = (env.get("POSITION_MODE") or "static").strip().lower()
    source = str(payload.get("source") or "")
    lat = _json_float(payload.get("lat"))
    lon = _json_float(payload.get("lon"))
    gpsd_host = str(payload.get("gpsd_host") or "")
    gpsd_port = _json_int(payload.get("gpsd_port"))
    expected_gpsd_host = (env.get("GPSD_HOST") or "127.0.0.1").strip()
    expected_gpsd_port = _env_int(env, "GPSD_PORT", 2947)
    expected_lat = _env_float(env, "BOX_LAT")
    expected_lon = _env_float(env, "BOX_LON")
    failures = payload.get("failures")
    failures_text = (
        ",".join(str(failure) for failure in failures) if isinstance(failures, list) else "-"
    )
    coords_ok = lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
    mode_ok = mode == expected_mode and source == expected_mode
    static_ok = True
    if expected_mode == "static":
        static_ok = (
            expected_lat is not None
            and expected_lon is not None
            and lat is not None
            and lon is not None
            and abs(lat - expected_lat) <= 0.0005
            and abs(lon - expected_lon) <= 0.0005
        )
    gpsd_ok = True
    if expected_mode == "gpsd":
        gpsd_ok = gpsd_host == expected_gpsd_host and gpsd_port == expected_gpsd_port
    ok = passed and coords_ok and mode_ok and static_ok and gpsd_ok
    return ProductionCheck(
        "position_runtime",
        ok,
        (
            f"passed={passed}, mode={mode or '-'}/{expected_mode}, "
            f"source={source or '-'}, position={_format_coord(lat, lon)}, "
            f"expected={_format_coord(expected_lat, expected_lon)}, "
            f"gpsd={gpsd_host or '-'}/{expected_gpsd_host}:{gpsd_port or '-'}/{expected_gpsd_port}, "
            f"failures={failures_text}"
        ),
    )


def _check_camera_report(
    path: Path,
    env: Mapping[str, str],
    *,
    hardware_profile_path: Path | None = None,
    require_camera_report: bool,
) -> ProductionCheck:
    if not require_camera_report:
        return ProductionCheck(
            "camera_runtime",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("camera_runtime", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("camera_runtime", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    device_index = _json_int(payload.get("device_index"))
    expected_device = _env_int(env, "CAMERA_DEVICE", 0)
    width = _json_int(payload.get("width"))
    height = _json_int(payload.get("height"))
    report_min_width = _json_int(payload.get("min_width")) or 640
    report_min_height = _json_int(payload.get("min_height")) or 480
    profile_min_width, profile_min_height = _hardware_camera_resolution(hardware_profile_path)
    min_width = max(report_min_width, profile_min_width or 0)
    min_height = max(report_min_height, profile_min_height or 0)
    failures = payload.get("failures")
    failures_text = (
        ",".join(str(failure) for failure in failures) if isinstance(failures, list) else "-"
    )
    ok = (
        passed
        and device_index == expected_device
        and width is not None
        and height is not None
        and width >= min_width
        and height >= min_height
    )
    return ProductionCheck(
        "camera_runtime",
        ok,
        (
            f"passed={passed}, device={device_index}/{expected_device}, "
            f"resolution={_format_resolution(width, height)}, "
            f"minimum={min_width}x{min_height}, "
            f"profile_min={_format_resolution(profile_min_width, profile_min_height)}, "
            f"failures={failures_text}"
        ),
    )


def _hardware_camera_resolution(path: Path | None) -> tuple[int | None, int | None]:
    if path is None or not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None, None
    camera = payload.get("camera") or {}
    return _parse_resolution(camera.get("resolution"))


def _parse_resolution(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, str) or "x" not in value:
        return None, None
    width, height = value.lower().split("x", 1)
    try:
        parsed_width = int(width.strip())
        parsed_height = int(height.strip())
    except ValueError:
        return None, None
    if parsed_width <= 0 or parsed_height <= 0:
        return None, None
    return parsed_width, parsed_height


def _check_network_report(
    path: Path,
    env: Mapping[str, str],
    *,
    require_network_report: bool,
    require_network_recovery: bool,
) -> ProductionCheck:
    if not require_network_report:
        return ProductionCheck(
            "network_runtime",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("network_runtime", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("network_runtime", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    target = str(payload.get("target") or "")
    expected_target = (env.get("NETWORK_PROBE_TARGET") or "1.1.1.1:443").strip()
    timeout_seconds = _json_float(payload.get("timeout_seconds"))
    expected_timeout = _env_float(env, "NETWORK_PROBE_TIMEOUT_SECONDS") or 3.0
    timeout_ok = timeout_seconds is not None and abs(timeout_seconds - expected_timeout) <= 0.1
    online = bool(payload.get("online"))
    recovery_configured = bool(payload.get("recovery_command_configured"))
    recovery_command = str(payload.get("recovery_command") or "").strip()
    expected_recovery_command = (env.get("NETWORK_RECOVERY_COMMAND") or "").strip()
    recovery_command_ok = (
        True
        if not require_network_recovery
        else bool(expected_recovery_command) and recovery_command == expected_recovery_command
    )
    failures = payload.get("failures")
    failures_text = (
        ",".join(str(failure) for failure in failures) if isinstance(failures, list) else "-"
    )
    ok = (
        passed
        and online
        and target == expected_target
        and timeout_ok
        and recovery_configured
        and recovery_command_ok
    )
    return ProductionCheck(
        "network_runtime",
        ok,
        (
            f"passed={passed}, target={target or '-'}/{expected_target}, "
            f"timeout={timeout_seconds or 0:.1f}/{expected_timeout:.1f}s, "
            f"online={online}, recovery_command={recovery_configured}, "
            f"command={recovery_command or '-'}/{expected_recovery_command or '-'}, "
            f"failures={failures_text}"
        ),
    )


def _check_power_report(
    path: Path,
    env: Mapping[str, str],
    *,
    require_power_report: bool,
) -> ProductionCheck:
    if not require_power_report:
        return ProductionCheck(
            "power_runtime",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("power_runtime", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("power_runtime", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    percent = _json_int(payload.get("battery_percent"))
    charging = payload.get("charging")
    source = str(payload.get("source") or "")
    capacity_wh = _json_float(payload.get("battery_capacity_wh"))
    available_wh = _json_float(payload.get("available_battery_wh"))
    critical_reserve_wh = _json_float(payload.get("critical_reserve_wh"))
    expected_capacity_wh = _env_float(env, "BATTERY_CAPACITY_WH")
    estimated_draw = _json_float(payload.get("estimated_draw_watts"))
    expected_draw = _env_float(env, "ESTIMATED_DRAW_WATTS") or 8.0
    estimated_runtime = _json_float(payload.get("estimated_runtime_hours"))
    required_runtime = _json_float(payload.get("required_runtime_hours"))
    expected_required_runtime = _env_float(env, "REQUIRED_RUNTIME_HOURS") or 10.0
    battery_critical = _env_int(env, "BATTERY_CRITICAL_PERCENT", 10)
    report_battery_critical = _json_int(payload.get("battery_critical_percent"))
    failures = payload.get("failures")
    failures_text = (
        ",".join(str(failure) for failure in failures) if isinstance(failures, list) else "-"
    )
    capacity_ok = (
        expected_capacity_wh is not None
        and capacity_wh is not None
        and abs(capacity_wh - expected_capacity_wh) <= 1.0
    )
    draw_ok = estimated_draw is not None and abs(estimated_draw - expected_draw) <= 0.1
    required_runtime_ok = (
        required_runtime is not None and abs(required_runtime - expected_required_runtime) <= 0.1
    )
    critical_threshold_ok = report_battery_critical == battery_critical
    expected_reserve_wh = (
        capacity_wh * (report_battery_critical / 100)
        if capacity_wh is not None
        and report_battery_critical is not None
        and 0 <= report_battery_critical <= 100
        else None
    )
    reserve_ok = (
        critical_reserve_wh is not None
        and expected_reserve_wh is not None
        and abs(critical_reserve_wh - expected_reserve_wh) <= 0.1
    )
    expected_available_wh = (
        capacity_wh * (max(0, percent - report_battery_critical) / 100)
        if capacity_wh is not None
        and percent is not None
        and report_battery_critical is not None
        and 0 <= percent <= 100
        and 0 <= report_battery_critical <= 100
        else None
    )
    expected_runtime = (
        available_wh / estimated_draw
        if available_wh is not None and estimated_draw is not None and estimated_draw > 0
        else None
    )
    available_ok = (
        available_wh is not None
        and expected_available_wh is not None
        and abs(available_wh - expected_available_wh) <= 0.1
    )
    runtime_consistent = (
        estimated_runtime is not None
        and expected_runtime is not None
        and abs(estimated_runtime - expected_runtime) <= 0.1
    )
    ok = (
        passed
        and source
        and percent is not None
        and percent > battery_critical
        and isinstance(charging, bool)
        and capacity_ok
        and draw_ok
        and required_runtime_ok
        and critical_threshold_ok
        and reserve_ok
        and available_ok
        and runtime_consistent
        and estimated_runtime is not None
        and estimated_runtime >= expected_required_runtime
    )
    return ProductionCheck(
        "power_runtime",
        ok,
        (
            f"passed={passed}, source={source or '-'}, battery={percent if percent is not None else '-'}%, "
            f"charging={charging if isinstance(charging, bool) else '-'}, "
            f"capacity={capacity_wh or 0:.1f}/{expected_capacity_wh or 0:.1f}Wh, "
            f"draw={estimated_draw or 0:.1f}/{expected_draw:.1f}W, "
            f"reserve={critical_reserve_wh or 0:.1f}/{expected_reserve_wh or 0:.1f}Wh, "
            f"available={available_wh or 0:.1f}/{expected_available_wh or 0:.1f}Wh, "
            f"runtime={estimated_runtime or 0:.1f}/{expected_required_runtime:.1f}h, "
            f"required={required_runtime or 0:.1f}/{expected_required_runtime:.1f}h, "
            f"critical={report_battery_critical if report_battery_critical is not None else '-'}/{battery_critical}%, "
            f"runtime_consistent={runtime_consistent}, "
            f"failures={failures_text}"
        ),
    )


def _check_disk_space(env: Mapping[str, str], path: Path) -> ProductionCheck:
    min_free_mb = _env_float(env, "BOX_DISK_MIN_FREE_MB") or 512
    path = _configured_event_log_path(env, path)
    status = DiskSpaceMonitor(path).check()
    if status is None:
        return ProductionCheck("disk_space", False, f"cannot inspect {path}")
    ok = status.free_mb >= min_free_mb
    return ProductionCheck(
        "disk_space",
        ok,
        f"{status.free_mb}MB free / required {min_free_mb:.0f}MB on {status.path}",
    )


def _check_state_path(env: Mapping[str, str], path: Path) -> ProductionCheck:
    configured = Path(env.get("BOX_STATE_PATH") or path)
    if not configured.is_absolute():
        return ProductionCheck(
            "state_path", False, f"BOX_STATE_PATH must be absolute: {configured}"
        )
    parent = configured.parent
    if not parent.exists():
        return ProductionCheck("state_path", False, f"missing parent {parent}")
    if not parent.is_dir():
        return ProductionCheck("state_path", False, f"parent is not a directory: {parent}")

    suffix = f"{configured.name}.readiness.{os.getpid()}"
    tmp_path = parent / f".{suffix}.tmp"
    check_path = parent / f".{suffix}.check"
    try:
        with tmp_path.open("w") as fp:
            fp.write("ready\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp_path, check_path)
        _fsync_directory(parent)
        check_path.unlink()
    except OSError as exc:
        return ProductionCheck("state_path", False, f"cannot write atomically in {parent}: {exc}")
    finally:
        for leftover in (tmp_path, check_path):
            try:
                leftover.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
    return ProductionCheck("state_path", True, f"atomic write ok: {configured}")


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _check_network_recovery(
    env: Mapping[str, str],
    *,
    require_network_recovery: bool,
) -> ProductionCheck:
    command = (env.get("NETWORK_RECOVERY_COMMAND") or "").strip()
    cooldown = _env_float(env, "NETWORK_RECOVERY_COOLDOWN_SECONDS") or 300.0
    timeout = _env_float(env, "NETWORK_RECOVERY_TIMEOUT_SECONDS") or 20.0
    if not require_network_recovery:
        return ProductionCheck(
            "network_recovery",
            True,
            "required=false" if not command else f"configured cooldown={cooldown:.0f}s",
        )
    ok = bool(command) and cooldown >= 30 and timeout > 0
    return ProductionCheck(
        "network_recovery",
        ok,
        (
            f"command={'configured' if command else 'missing'}, "
            f"cooldown={cooldown:.0f}s, timeout={timeout:.1f}s"
        ),
    )


def _check_notification_webhook(
    env: Mapping[str, str],
    *,
    require_notification_webhook: bool,
) -> ProductionCheck:
    webhook = (env.get("BORING_NOTIFY_WEBHOOK_URL") or env.get("NTFY_WEBHOOK_URL") or "").strip()
    if not require_notification_webhook:
        return ProductionCheck(
            "notification_webhook",
            True,
            "required=false" if not webhook else "configured",
        )
    ok = webhook.startswith("https://") or webhook.startswith("http://")
    return ProductionCheck(
        "notification_webhook",
        ok,
        "configured" if ok else "missing BORING_NOTIFY_WEBHOOK_URL or NTFY_WEBHOOK_URL",
    )


def _notification_webhook_host(env: Mapping[str, str]) -> str | None:
    webhook = (env.get("BORING_NOTIFY_WEBHOOK_URL") or env.get("NTFY_WEBHOOK_URL") or "").strip()
    if not webhook:
        return None
    return urlparse(webhook).netloc or None


def _notification_webhook_hash(env: Mapping[str, str]) -> str | None:
    webhook = (env.get("BORING_NOTIFY_WEBHOOK_URL") or env.get("NTFY_WEBHOOK_URL") or "").strip()
    if not webhook:
        return None
    return hashlib.sha256(webhook.encode("utf-8")).hexdigest()


def _check_notification_report(
    path: Path,
    *,
    expected_webhook_host: str | None = None,
    expected_webhook_hash: str | None = None,
    require_notification_test: bool,
) -> ProductionCheck:
    if not require_notification_test:
        return ProductionCheck(
            "notification_test",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("notification_test", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("notification_test", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    status_code = payload.get("status_code")
    host = str(payload.get("webhook_host") or "unknown")
    webhook_hash = str(payload.get("webhook_hash") or "")
    title = str(payload.get("title") or "")
    message = str(payload.get("message") or "")
    sound = payload.get("sound") is True
    tested_at = _parse_timestamp(payload.get("tested_at"))
    error = payload.get("error")
    host_ok = expected_webhook_host is None or host == expected_webhook_host
    hash_ok = expected_webhook_hash is None or webhook_hash == expected_webhook_hash
    battery_message_ok = _is_battery_notification_text(f"{title} {message}")
    ok = (
        passed
        and isinstance(status_code, int)
        and 200 <= status_code < 300
        and host_ok
        and hash_ok
        and sound
        and tested_at is not None
        and battery_message_ok
    )
    return ProductionCheck(
        "notification_test",
        ok,
        (
            f"passed={passed}, status={status_code}, host={host}, "
            f"expected_host={expected_webhook_host or '-'}, "
            f"hash={_hash_status(webhook_hash, hash_ok)}, "
            f"sound={sound}, "
            f"tested_at={'ok' if tested_at is not None else 'missing'}, "
            f"battery_message={battery_message_ok}, error={error or '-'}"
        ),
    )


def _hash_status(value: str, ok: bool) -> str:
    if not value:
        return "missing"
    return "ok" if ok else "mismatch"


def _is_battery_notification_text(value: str) -> bool:
    normalized = value.lower()
    has_battery = any(token in normalized for token in ("batterie", "battery"))
    has_low = any(token in normalized for token in ("faible", "low", "manquer"))
    return has_battery and has_low


def _check_autopay_smoke_report(
    path: Path,
    *,
    env: Mapping[str, str],
    require_autopay_smoke: bool,
) -> ProductionCheck:
    if not require_autopay_smoke:
        return ProductionCheck(
            "autopay_smoke",
            True,
            "required=false" if not path.exists() else str(path),
        )
    if not path.exists():
        return ProductionCheck("autopay_smoke", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("autopay_smoke", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    dry_run = bool(payload.get("dry_run"))
    active_verified = bool(payload.get("active_session_verified"))
    stopped = bool(payload.get("stopped"))
    stop_verified = bool(payload.get("stop_verified"))
    amount_cents = payload.get("amount_cents")
    amount_ok = isinstance(amount_cents, int) and amount_cents > 0
    active_amount = payload.get("active_session_amount_cents")
    amount_verified = payload.get("amount_verified") is True
    active_amount_ok = (
        isinstance(active_amount, int) and amount_ok and active_amount == amount_cents
    )
    max_session_amount = int(_env_float(env, "MAX_SESSION_AMOUNT_CENTS") or 500)
    max_session_ok = max_session_amount > 0 and amount_ok and amount_cents <= max_session_amount
    duration_minutes = payload.get("duration_minutes")
    expected_duration = int(_env_float(env, "DEFAULT_DURATION_MINUTES") or 15)
    duration_ok = isinstance(duration_minutes, int) and duration_minutes == expected_duration
    active_duration = _json_int(payload.get("active_session_duration_minutes"))
    duration_verified = payload.get("duration_verified") is True
    active_duration_ok = active_duration == expected_duration
    smoke_lat = _json_float(payload.get("lat"))
    smoke_lon = _json_float(payload.get("lon"))
    expected_lat = _env_float(env, "BOX_LAT")
    expected_lon = _env_float(env, "BOX_LON")
    position_ok = (
        smoke_lat is not None
        and smoke_lon is not None
        and expected_lat is not None
        and expected_lon is not None
        and abs(smoke_lat - expected_lat) <= 0.0005
        and abs(smoke_lon - expected_lon) <= 0.0005
    )
    provider = str(payload.get("provider") or "unknown")
    expected_provider = (env.get("PAYMENT_PROVIDER") or "paybyphone").strip().lower()
    provider_ok = provider.lower() == expected_provider
    plate = str(payload.get("plate") or "")
    expected_plate = (env.get("DEFAULT_VEHICLE_PLATE") or "AA-000-AA").strip()
    plate_ok = plate == expected_plate
    zone_id = payload.get("zone_id")
    session_location_id = payload.get("session_location_id")
    session_zone_ok = bool(zone_id) and session_location_id == zone_id
    expected_zone_id = (env.get("PAYBYPHONE_LOCATION_ID") or "").strip()
    zone_ok = session_zone_ok and (not expected_zone_id or zone_id == expected_zone_id)
    error = payload.get("error")
    ok = (
        passed
        and not dry_run
        and active_verified
        and stopped
        and stop_verified
        and amount_ok
        and amount_verified
        and active_amount_ok
        and max_session_ok
        and duration_ok
        and duration_verified
        and active_duration_ok
        and position_ok
        and provider_ok
        and plate_ok
        and zone_ok
    )
    return ProductionCheck(
        "autopay_smoke",
        ok,
        (
            f"passed={passed}, dry_run={dry_run}, active={active_verified}, "
            f"stopped={stopped}, stop_verified={stop_verified}, "
            f"amount={amount_cents}/{active_amount}/{max_session_amount}, "
            f"amount_verified={amount_verified}, "
            f"duration={duration_minutes}/{expected_duration}, "
            f"active_duration={active_duration if active_duration is not None else '-'}/{expected_duration}, "
            f"duration_verified={duration_verified}, "
            f"position={_format_coord(smoke_lat, smoke_lon)}/{_format_coord(expected_lat, expected_lon)}, "
            f"provider={provider}/{expected_provider}, "
            f"plate={plate or '-'}/{expected_plate}, "
            f"zone={zone_id or '-'}/{expected_zone_id or '-'}, "
            f"session_zone={session_location_id or '-'}/{zone_id or '-'}, "
            f"error={error or '-'}"
        ),
    )


def _hardware_required_benchmark_fps(path: Path) -> float | None:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    runtime = payload.get("runtime") or {}
    return _json_float(runtime.get("min_benchmark_fps"))


def _check_benchmark_report(
    path: Path,
    *,
    required_min_fps: float | None = None,
    expected_model_path: Path | None = None,
) -> ProductionCheck:
    if not path.exists():
        return ProductionCheck("vision_benchmark", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("vision_benchmark", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    frames_processed = int(payload.get("frames_processed") or 0)
    detections_seen = int(payload.get("detections_seen") or 0)
    measured_fps = float(payload.get("measured_fps") or 0)
    min_fps = float(payload.get("min_fps") or 0)
    required_fps = required_min_fps if required_min_fps is not None else min_fps
    device = str(payload.get("device") or "unknown")
    report_model = str(payload.get("model_path") or "")
    target_labels = payload.get("target_labels")
    target_ok = isinstance(target_labels, list) and "control_vehicle" in target_labels
    model_ok = expected_model_path is None or _same_path(report_model, expected_model_path)
    ok = (
        passed
        and frames_processed > 0
        and detections_seen > 0
        and min_fps >= required_fps
        and measured_fps >= required_fps
        and target_ok
        and model_ok
    )
    return ProductionCheck(
        "vision_benchmark",
        ok,
        (
            f"passed={passed}, fps={measured_fps:.2f}/{min_fps:.2f}, "
            f"required={required_fps:.2f}, "
            f"frames={frames_processed}, detections={detections_seen}, device={device}, "
            f"target={','.join(str(label) for label in target_labels) if isinstance(target_labels, list) else '-'}/control_vehicle, "
            f"model={report_model or '-'}/{expected_model_path or '-'}"
        ),
    )


def _check_vision_eval_report(
    path: Path,
    *,
    expected_model_path: Path | None = None,
    expected_dataset_path: Path | None = None,
) -> ProductionCheck:
    if not path.exists():
        return ProductionCheck("vision_eval", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("vision_eval", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    recall = _json_float(payload.get("recall")) or 0.0
    min_recall = _json_float(payload.get("min_recall")) or 0.90
    false_positive_per_hour = _json_float(payload.get("false_positive_per_hour")) or 0.0
    max_false_positive_per_hour = _json_float(payload.get("max_false_positive_per_hour")) or 1.0
    evaluated_hours = _json_float(payload.get("evaluated_hours")) or 0.0
    frames_evaluated = int(payload.get("frames_evaluated") or 0)
    positive_frames = int(payload.get("positive_frames_evaluated") or 0)
    negative_frames = int(payload.get("negative_frames_evaluated") or 0)
    negative_hours = _json_float(payload.get("negative_evaluated_hours")) or 0.0
    true_positives = int(payload.get("true_positives") or 0)
    false_positives = int(payload.get("false_positives") or 0)
    false_negatives = int(payload.get("false_negatives") or 0)
    invalid_images = int(payload.get("invalid_images") or 0)
    invalid_labels = int(payload.get("invalid_labels") or 0)
    precision = _json_float(payload.get("precision")) or 0.0
    expected_recall = _ratio(true_positives, true_positives + false_negatives)
    expected_precision = _ratio(true_positives, true_positives + false_positives)
    expected_fp_per_hour = false_positives / negative_hours if negative_hours > 0 else None
    frame_coverage_consistent = frames_evaluated == positive_frames + negative_frames
    metrics_consistent = (
        expected_recall is not None
        and abs(recall - expected_recall) <= 0.001
        and expected_precision is not None
        and abs(precision - expected_precision) <= 0.001
        and expected_fp_per_hour is not None
        and abs(false_positive_per_hour - expected_fp_per_hour) <= 0.001
        and frame_coverage_consistent
    )
    report_model = str(payload.get("model_path") or "")
    model_ok = expected_model_path is None or _same_path(report_model, expected_model_path)
    report_dataset = str(payload.get("dataset_path") or "")
    dataset_ok = expected_dataset_path is None or _same_path(
        report_dataset,
        expected_dataset_path,
    )
    required_class = str(payload.get("required_class") or "")
    class_ok = required_class == "control_vehicle"
    ok = (
        passed
        and recall >= min_recall
        and false_positive_per_hour <= max_false_positive_per_hour
        and evaluated_hours > 0
        and frames_evaluated > 0
        and positive_frames > 0
        and negative_frames > 0
        and negative_hours > 0
        and true_positives > 0
        and invalid_images == 0
        and invalid_labels == 0
        and metrics_consistent
        and model_ok
        and dataset_ok
        and class_ok
    )
    return ProductionCheck(
        "vision_eval",
        ok,
        (
            f"passed={passed}, recall={recall:.3f}/{min_recall:.3f}, "
            f"fp_per_hour={false_positive_per_hour:.2f}/{max_false_positive_per_hour:.2f}, "
            f"hours={evaluated_hours:.1f}, frames={frames_evaluated}, "
            f"positive_frames={positive_frames}, negative_frames={negative_frames}, "
            f"negative_hours={negative_hours:.1f}, "
            f"true_positives={true_positives}, false_positives={false_positives}, "
            f"false_negatives={false_negatives}, invalid_images={invalid_images}, "
            f"invalid_labels={invalid_labels}, "
            f"metrics_consistent={metrics_consistent}, "
            f"class={required_class or '-'}/control_vehicle, "
            f"model={report_model or '-'}/{expected_model_path or '-'}, "
            f"dataset={report_dataset or '-'}/{expected_dataset_path or '-'}"
        ),
    )


def _check_burn_in_report(
    env: Mapping[str, str],
    path: Path,
    *,
    min_burn_in_hours: float,
    require_charging_seen: bool,
) -> ProductionCheck:
    if not path.exists():
        return ProductionCheck("burn_in", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("burn_in", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    requested_duration_seconds = _json_float(payload.get("requested_duration_seconds"))
    duration_hours = float(payload.get("duration_seconds") or 0) / 3600
    interval_seconds = _json_float(payload.get("interval_seconds"))
    max_sample_gap_seconds = _json_float(payload.get("max_sample_gap_seconds"))
    sample_count = int(payload.get("sample_count") or 0)
    camera_failures = int(payload.get("camera_failures") or 0)
    network_failures = int(payload.get("network_failures") or 0)
    start_battery = _json_float(payload.get("start_battery_percent"))
    end_battery = _json_float(payload.get("end_battery_percent"))
    min_battery = _json_float(payload.get("min_battery_percent"))
    battery_delta = _json_float(payload.get("battery_delta_percent"))
    max_temp_c = _json_float(payload.get("max_temp_c"))
    report_thermal_warning_c = _json_float(payload.get("thermal_warning_c"))
    report_thermal_critical_c = _json_float(payload.get("thermal_critical_c"))
    report_battery_low_percent = _json_int(payload.get("battery_low_percent"))
    report_battery_critical_percent = _json_int(payload.get("battery_critical_percent"))
    thermal_warning_c = _env_float(env, "THERMAL_WARNING_C") or 75.0
    thermal_critical_c = _env_float(env, "THERMAL_CRITICAL_C") or 85.0
    battery_low_percent = _env_int(env, "BATTERY_LOW_PERCENT", 25)
    battery_critical_percent = _env_int(env, "BATTERY_CRITICAL_PERCENT", 10)
    thresholds_ok = (
        report_thermal_warning_c == thermal_warning_c
        and report_thermal_critical_c == thermal_critical_c
        and report_battery_low_percent == battery_low_percent
        and report_battery_critical_percent == battery_critical_percent
    )
    requested_duration_ok = (
        requested_duration_seconds is not None
        and requested_duration_seconds > 0
        and duration_hours * 3600 + 1.0 >= requested_duration_seconds
    )
    cadence_config_ok = (
        interval_seconds is not None
        and interval_seconds > 0
        and max_sample_gap_seconds is not None
        and max_sample_gap_seconds >= interval_seconds
    )
    battery_low = bool(payload.get("battery_low_seen"))
    battery_critical = bool(payload.get("battery_critical_seen"))
    thermal_critical = bool(payload.get("thermal_critical_seen"))
    min_above_low = min_battery is not None and min_battery > battery_low_percent
    min_above_critical = min_battery is not None and min_battery > battery_critical_percent
    charging_seen = bool(payload.get("charging_seen"))
    discharging_seen = bool(payload.get("discharging_seen"))
    charging_ok = charging_seen if require_charging_seen else True
    discharging_ok = discharging_seen if require_charging_seen else True
    ok = (
        passed
        and requested_duration_ok
        and duration_hours >= min_burn_in_hours
        and cadence_config_ok
        and sample_count > 0
        and camera_failures == 0
        and network_failures == 0
        and start_battery is not None
        and end_battery is not None
        and min_battery is not None
        and battery_delta is not None
        and max_temp_c is not None
        and thresholds_ok
        and max_temp_c < thermal_critical_c
        and not battery_low
        and not battery_critical
        and min_above_low
        and min_above_critical
        and not thermal_critical
        and charging_ok
        and discharging_ok
    )
    return ProductionCheck(
        "burn_in",
        ok,
        (
            f"passed={passed}, duration={duration_hours:.1f}h/{min_burn_in_hours:.1f}h, "
            f"requested_duration={_format_seconds(requested_duration_seconds)}, "
            f"interval={_format_seconds(interval_seconds)}, "
            f"max_sample_gap={_format_seconds(max_sample_gap_seconds)}, "
            f"samples={sample_count}, "
            f"camera_failures={camera_failures}, network_failures={network_failures}, "
            f"battery={_format_battery(start_battery, end_battery, min_battery, battery_delta)}, "
            f"min_above_low={min_above_low}({battery_low_percent}%), "
            f"min_above_critical={min_above_critical}({battery_critical_percent}%), "
            f"max_temp={_format_temp(max_temp_c)}/{thermal_critical_c:.1f}C, "
            f"thresholds_ok={thresholds_ok}, "
            f"battery_low={battery_low}, battery_critical={battery_critical}, "
            f"thermal_critical={thermal_critical}, "
            f"charging_seen={charging_seen}, discharging_seen={discharging_seen}"
        ),
    )


def _check_burn_in_samples(burn_in_report_path: Path) -> ProductionCheck:
    samples_path = burn_in_report_path.with_name("samples.jsonl")
    if not samples_path.exists():
        return ProductionCheck("burn_in_samples", False, f"missing {samples_path}")
    try:
        report = json.loads(burn_in_report_path.read_text())
    except FileNotFoundError:
        return ProductionCheck("burn_in_samples", False, f"missing report {burn_in_report_path}")
    except json.JSONDecodeError:
        return ProductionCheck(
            "burn_in_samples", False, f"invalid report json {burn_in_report_path}"
        )
    if not isinstance(report, dict):
        return ProductionCheck("burn_in_samples", False, "invalid report payload")

    expected_sample_count = int(report.get("sample_count") or 0)
    expected_camera_failures = int(report.get("camera_failures") or 0)
    expected_network_failures = int(report.get("network_failures") or 0)
    expected_start_battery = _json_float(report.get("start_battery_percent"))
    expected_end_battery = _json_float(report.get("end_battery_percent"))
    expected_min_battery = _json_float(report.get("min_battery_percent"))
    expected_battery_delta = _json_float(report.get("battery_delta_percent"))
    expected_charging_seen = bool(report.get("charging_seen"))
    expected_discharging_seen = bool(report.get("discharging_seen"))
    expected_max_temp = _json_float(report.get("max_temp_c"))
    expected_max_sample_gap = _json_float(report.get("max_sample_gap_seconds"))
    started_at = _parse_timestamp(report.get("started_at"))
    ended_at = _parse_timestamp(report.get("ended_at"))
    invalid_lines = 0
    scanned = 0
    camera_failures = 0
    network_failures = 0
    battery_values: list[float] = []
    charging_values: list[bool] = []
    temp_values: list[float] = []
    timestamps: list[datetime] = []
    for line_number, raw_line in enumerate(samples_path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            sample = json.loads(raw_line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(sample, dict):
            invalid_lines += 1
            continue
        scanned += 1
        timestamp = _parse_timestamp(sample.get("ts"))
        if timestamp is None:
            invalid_lines += 1
            continue
        timestamps.append(timestamp.astimezone(timezone.utc))
        if sample.get("camera_ok") is not True:
            camera_failures += 1
        if sample.get("network_online") is not True:
            network_failures += 1
        battery = _json_float(sample.get("battery_percent"))
        if battery is not None:
            battery_values.append(battery)
        charging = sample.get("battery_charging")
        if isinstance(charging, bool):
            charging_values.append(charging)
        temp = _json_float(sample.get("temp_c"))
        if temp is not None:
            temp_values.append(temp)

    start_battery = battery_values[0] if battery_values else None
    end_battery = battery_values[-1] if battery_values else None
    min_battery = min(battery_values) if battery_values else None
    battery_delta = (
        end_battery - start_battery
        if start_battery is not None and end_battery is not None
        else None
    )
    charging_seen = any(value is True for value in charging_values)
    discharging_seen = any(value is False for value in charging_values)
    max_temp = max(temp_values) if temp_values else None
    timestamps_monotonic = all(
        previous <= current for previous, current in zip(timestamps, timestamps[1:])
    )
    max_observed_gap = _max_timestamp_gap_seconds(timestamps)
    timestamps_in_window = (
        started_at is not None
        and ended_at is not None
        and len(timestamps) == scanned
        and all(started_at <= timestamp <= ended_at for timestamp in timestamps)
    )
    cadence_ok = (
        expected_max_sample_gap is not None
        and max_observed_gap is not None
        and max_observed_gap <= expected_max_sample_gap
    )
    sample_count_ok = scanned == expected_sample_count
    camera_ok = camera_failures == expected_camera_failures == 0
    network_ok = network_failures == expected_network_failures == 0
    battery_ok = (
        start_battery is not None
        and start_battery == expected_start_battery
        and end_battery is not None
        and end_battery == expected_end_battery
        and min_battery is not None
        and min_battery == expected_min_battery
        and battery_delta is not None
        and battery_delta == expected_battery_delta
        and charging_seen == expected_charging_seen
        and discharging_seen == expected_discharging_seen
    )
    temp_ok = max_temp is not None and max_temp == expected_max_temp
    ok = (
        invalid_lines == 0
        and scanned > 0
        and sample_count_ok
        and camera_ok
        and network_ok
        and battery_ok
        and temp_ok
        and timestamps_monotonic
        and timestamps_in_window
        and cadence_ok
    )
    return ProductionCheck(
        "burn_in_samples",
        ok,
        (
            f"scanned={scanned}/{expected_sample_count}, "
            f"camera_failures={camera_failures}/{expected_camera_failures}, "
            f"network_failures={network_failures}/{expected_network_failures}, "
            f"start_battery={_format_percent(start_battery)}/{_format_percent(expected_start_battery)}, "
            f"end_battery={_format_percent(end_battery)}/{_format_percent(expected_end_battery)}, "
            f"min_battery={_format_percent(min_battery)}/{_format_percent(expected_min_battery)}, "
            f"battery_delta={_format_delta(battery_delta)}/{_format_delta(expected_battery_delta)}, "
            f"charging_seen={charging_seen}/{expected_charging_seen}, "
            f"discharging_seen={discharging_seen}/{expected_discharging_seen}, "
            f"max_temp={_format_temp(max_temp)}/{_format_temp(expected_max_temp)}, "
            f"max_sample_gap={_format_seconds(max_observed_gap)}/{_format_seconds(expected_max_sample_gap)}, "
            f"timestamps_monotonic={timestamps_monotonic}, "
            f"timestamps_in_window={timestamps_in_window}, "
            f"cadence_ok={cadence_ok}, "
            f"invalid_lines={invalid_lines}"
        ),
    )


def _max_timestamp_gap_seconds(timestamps: list[datetime]) -> float | None:
    if not timestamps:
        return None
    if len(timestamps) == 1:
        return 0.0
    return max(
        (current - previous).total_seconds()
        for previous, current in zip(timestamps, timestamps[1:])
    )


def _check_runtime_event_log(
    env: Mapping[str, str],
    event_log_path: Path,
    burn_in_report_path: Path,
    *,
    require_runtime_event_log: bool,
    max_heartbeat_gap_seconds: float,
) -> ProductionCheck:
    event_log_path = _configured_event_log_path(env, event_log_path)
    event_log_path = _event_log_path(event_log_path)
    if not event_log_path.exists():
        return ProductionCheck(
            "runtime_event_log",
            not require_runtime_event_log,
            f"missing {'required' if require_runtime_event_log else 'optional'} {event_log_path}",
        )
    if not event_log_path.is_file():
        return ProductionCheck(
            "runtime_event_log",
            not require_runtime_event_log,
            f"not a file: {event_log_path}",
        )
    started_at, ended_at = _burn_in_window(burn_in_report_path)
    failures: list[str] = []
    scanned = 0
    heartbeat_seen = False
    earliest_heartbeat: datetime | None = None
    latest_heartbeat: datetime | None = None
    for line_number, raw_line in enumerate(event_log_path.read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            failures.append(f"line{line_number}=invalid_json")
            continue
        if not isinstance(event, dict):
            failures.append(f"line{line_number}=invalid_payload")
            continue
        timestamp = _parse_timestamp(event.get("ts"))
        if started_at is not None and timestamp is not None:
            if timestamp.astimezone(timezone.utc) < started_at:
                continue
        name = str(event.get("event") or "")
        scanned += 1
        if name == "heartbeat":
            heartbeat_seen = True
            if timestamp is not None:
                timestamp = timestamp.astimezone(timezone.utc)
                if earliest_heartbeat is None or timestamp < earliest_heartbeat:
                    earliest_heartbeat = timestamp
                if latest_heartbeat is None or timestamp > latest_heartbeat:
                    latest_heartbeat = timestamp
        if name in BLOCKING_RUNTIME_EVENTS:
            failures.append(f"{name}@line{line_number}")
        elif name == "network_recovery_attempted" and event.get("ok") is False:
            failures.append(f"network_recovery_failed@line{line_number}")

    heartbeat_start_gap_seconds = (
        (earliest_heartbeat - started_at).total_seconds()
        if started_at is not None and earliest_heartbeat is not None
        else None
    )
    heartbeat_end_gap_seconds = (
        (ended_at - latest_heartbeat).total_seconds()
        if ended_at is not None and latest_heartbeat is not None
        else None
    )
    heartbeat_covers_window = (
        heartbeat_start_gap_seconds is not None
        and heartbeat_end_gap_seconds is not None
        and heartbeat_start_gap_seconds <= max_heartbeat_gap_seconds
        and heartbeat_end_gap_seconds <= max_heartbeat_gap_seconds
    )
    return ProductionCheck(
        "runtime_event_log",
        scanned > 0 and heartbeat_seen and heartbeat_covers_window and not failures,
        (
            f"scanned={scanned}, since={started_at.isoformat() if started_at else '-'}, "
            f"heartbeat={heartbeat_seen}, "
            f"heartbeat_start_gap={_format_seconds(heartbeat_start_gap_seconds)}/{max_heartbeat_gap_seconds:.0f}s, "
            f"heartbeat_end_gap={_format_seconds(heartbeat_end_gap_seconds)}/{max_heartbeat_gap_seconds:.0f}s, "
            f"failures={', '.join(failures) if failures else '-'}"
        ),
    )


def _event_log_path(path: Path) -> Path:
    if path.exists() and path.is_dir():
        return path / "events.jsonl"
    return path


def _configured_event_log_path(env: Mapping[str, str], path: Path) -> Path:
    return Path(env.get("BOX_EVENT_LOG_PATH") or path)


def _burn_in_window(path: Path) -> tuple[datetime | None, datetime | None]:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, dict):
        return None, None
    return _parse_timestamp(payload.get("started_at")), _parse_timestamp(payload.get("ended_at"))


def _check_report_freshness(
    env: Mapping[str, str],
    *,
    now: datetime,
    systemd_report_path: Path,
    position_report_path: Path,
    camera_report_path: Path,
    network_report_path: Path,
    power_report_path: Path,
    vision_eval_report_path: Path,
    benchmark_report_path: Path,
    autopay_smoke_report_path: Path,
    notification_report_path: Path,
    burn_in_report_path: Path,
    require_systemd_report: bool,
    require_position_report: bool,
    require_camera_report: bool,
    require_network_report: bool,
    require_power_report: bool,
    require_autopay_smoke: bool,
    require_notification_test: bool,
) -> ProductionCheck:
    max_age_hours = _env_float(env, "BOX_READINESS_MAX_REPORT_AGE_HOURS")
    if max_age_hours is None:
        max_age_hours = 72.0
    if max_age_hours <= 0:
        return ProductionCheck("report_freshness", True, "disabled")

    reports: list[tuple[str, Path]] = [
        ("vision_eval", vision_eval_report_path),
        ("vision_benchmark", benchmark_report_path),
        ("burn_in", burn_in_report_path),
    ]
    if require_systemd_report:
        reports.append(("systemd_runtime", systemd_report_path))
    if require_position_report:
        reports.append(("position_runtime", position_report_path))
    if require_camera_report:
        reports.append(("camera_runtime", camera_report_path))
    if require_network_report:
        reports.append(("network_runtime", network_report_path))
    if require_power_report:
        reports.append(("power_runtime", power_report_path))
    if require_autopay_smoke:
        reports.append(("autopay_smoke", autopay_smoke_report_path))
    if require_notification_test:
        reports.append(("notification_test", notification_report_path))

    failures: list[str] = []
    ages: list[str] = []
    for name, path in reports:
        try:
            payload = json.loads(path.read_text())
        except FileNotFoundError:
            failures.append(f"{name}=missing")
            continue
        except json.JSONDecodeError:
            failures.append(f"{name}=invalid_json")
            continue
        if not isinstance(payload, dict):
            failures.append(f"{name}=invalid_payload")
            continue
        timestamp = _report_timestamp(payload)
        if timestamp is None:
            failures.append(f"{name}=missing_timestamp")
            continue
        timestamp = timestamp.astimezone(timezone.utc)
        age_hours = (now.astimezone(timezone.utc) - timestamp).total_seconds() / 3600
        ages.append(f"{name}={age_hours:.1f}h")
        if age_hours < -0.1:
            failures.append(f"{name}=future_timestamp")
        elif age_hours > max_age_hours:
            failures.append(f"{name}={age_hours:.1f}h>{max_age_hours:.1f}h")

    return ProductionCheck(
        "report_freshness",
        not failures,
        (
            f"max_age={max_age_hours:.1f}h, "
            f"ages={', '.join(ages) if ages else '-'}, "
            f"failures={', '.join(failures) if failures else '-'}"
        ),
    )


def _report_timestamp(payload: Mapping[str, object]) -> datetime | None:
    for key in ("checked_at", "tested_at", "generated_at", "ended_at"):
        value = payload.get(key)
        timestamp = _parse_timestamp(value)
        if timestamp is not None:
            return timestamp
    return None


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _env_float(env: Mapping[str, str], name: str) -> float | None:
    value = env.get(name)
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _json_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _duration_seconds(value: str) -> float | None:
    raw = value.strip().lower()
    if not raw:
        return None
    try:
        if raw.endswith("ms"):
            return float(raw[:-2]) / 1000
        if raw.endswith("min"):
            return float(raw[:-3]) * 60
        if raw.endswith("s"):
            return float(raw[:-1])
        return float(raw)
    except ValueError:
        return None


def _format_coord(lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "-"
    return f"{lat:.5f},{lon:.5f}"


def _format_resolution(width: int | None, height: int | None) -> str:
    if width is None or height is None:
        return "-"
    return f"{width}x{height}"


def _format_temp(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}C"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}%"


def _format_delta(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.0f}%"


def _format_battery(
    start: float | None,
    end: float | None,
    minimum: float | None,
    delta: float | None,
) -> str:
    if start is None or end is None or minimum is None or delta is None:
        return "-"
    return f"start={start:.0f}%, end={end:.0f}%, min={minimum:.0f}%, delta={delta:.0f}%"


def _format_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}s"


def _format_hours(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}h"


def _same_path(reported: str, expected: Path) -> bool:
    if not reported.strip():
        return False
    try:
        return Path(reported).expanduser().resolve(strict=False) == expected.expanduser().resolve(
            strict=False
        )
    except OSError:
        return False
