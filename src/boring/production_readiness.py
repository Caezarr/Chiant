"""Gate final de readiness pour installer une box dans une voiture."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from boring.autopay_readiness import audit_autopay_readiness
from boring.hardware_profile import audit_hardware_profile
from boring.power_budget import build_power_budget
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
    vision_eval_report_path: Path = Path("reports/vision-eval.json"),
    benchmark_report_path: Path = Path("reports/vision-benchmark.json"),
    autopay_smoke_report_path: Path = Path("reports/autopay-smoke.json"),
    notification_report_path: Path = Path("reports/notification-test.json"),
    burn_in_report_path: Path = Path("burn-in/report.json"),
    storage_path: Path = Path("/var/lib/boring/events.jsonl"),
    require_edge_export: bool = True,
    require_real_payment: bool = True,
    require_autopay_smoke: bool = True,
    require_charging_seen: bool = True,
    require_network_recovery: bool = True,
    require_notification_webhook: bool = True,
    require_notification_test: bool = True,
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
        _summary_check("vision", vision.passed, _failed_names(vision.checks)),
        _summary_check("autopay", autopay.passed, _failed_names(autopay.checks)),
        _check_autopay_smoke_report(
            autopay_smoke_report_path,
            env=values,
            require_autopay_smoke=require_autopay_smoke,
        ),
        _summary_check("hardware", hardware.passed, _failed_names(hardware.checks)),
        _check_hardware_env_consistency(values, hardware_profile_path),
        _check_vision_eval_report(vision_eval_report_path),
        _check_benchmark_report(
            benchmark_report_path,
            required_min_fps=_hardware_required_benchmark_fps(hardware_profile_path),
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
            require_notification_test=require_notification_test,
        ),
        _check_disk_space(values, storage_path),
        _check_burn_in_report(
            burn_in_report_path,
            min_burn_in_hours=min_burn_in_hours,
            require_charging_seen=require_charging_seen,
        ),
        _check_runtime_event_log(storage_path, burn_in_report_path),
        _check_report_freshness(
            values,
            now=checked_at,
            vision_eval_report_path=vision_eval_report_path,
            benchmark_report_path=benchmark_report_path,
            autopay_smoke_report_path=autopay_smoke_report_path,
            notification_report_path=notification_report_path,
            burn_in_report_path=burn_in_report_path,
            require_autopay_smoke=require_autopay_smoke,
            require_notification_test=require_notification_test,
        ),
    ]
    return ProductionReadinessReport(checks)


def write_report(report: ProductionReadinessReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _summary_check(name: str, ok: bool, failures: str) -> ProductionCheck:
    return ProductionCheck(name, ok, "ok" if ok else f"failed: {failures}")


def _failed_names(checks) -> str:
    names = [check.name for check in checks if not check.ok]
    return ", ".join(names) if names else "none"


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
            f"daily_supported={budget.daily_supported_runtime_hours:.1f}h"
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


def _check_disk_space(env: Mapping[str, str], path: Path) -> ProductionCheck:
    min_free_mb = _env_float(env, "BOX_DISK_MIN_FREE_MB") or 512
    status = DiskSpaceMonitor(path).check()
    if status is None:
        return ProductionCheck("disk_space", False, f"cannot inspect {path}")
    ok = status.free_mb >= min_free_mb
    return ProductionCheck(
        "disk_space",
        ok,
        f"{status.free_mb}MB free / required {min_free_mb:.0f}MB on {status.path}",
    )


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


def _check_notification_report(
    path: Path,
    *,
    expected_webhook_host: str | None = None,
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
    error = payload.get("error")
    host_ok = expected_webhook_host is None or host == expected_webhook_host
    ok = passed and isinstance(status_code, int) and 200 <= status_code < 300 and host_ok
    return ProductionCheck(
        "notification_test",
        ok,
        (
            f"passed={passed}, status={status_code}, host={host}, "
            f"expected_host={expected_webhook_host or '-'}, error={error or '-'}"
        ),
    )


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
    provider = str(payload.get("provider") or "unknown")
    expected_provider = (env.get("PAYMENT_PROVIDER") or "paybyphone").strip().lower()
    provider_ok = provider.lower() == expected_provider
    plate = str(payload.get("plate") or "")
    expected_plate = (env.get("DEFAULT_VEHICLE_PLATE") or "AA-000-AA").strip()
    plate_ok = plate == expected_plate
    zone_id = payload.get("zone_id")
    expected_zone_id = (env.get("PAYBYPHONE_LOCATION_ID") or "").strip()
    zone_ok = not expected_zone_id or zone_id == expected_zone_id
    error = payload.get("error")
    ok = (
        passed
        and not dry_run
        and active_verified
        and stopped
        and stop_verified
        and amount_ok
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
            f"amount={amount_cents}, provider={provider}/{expected_provider}, "
            f"plate={plate or '-'}/{expected_plate}, "
            f"zone={zone_id or '-'}/{expected_zone_id or '-'}, "
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
    path: Path, *, required_min_fps: float | None = None
) -> ProductionCheck:
    if not path.exists():
        return ProductionCheck("vision_benchmark", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return ProductionCheck("vision_benchmark", False, f"invalid json {path}")

    passed = bool(payload.get("passed"))
    frames_processed = int(payload.get("frames_processed") or 0)
    measured_fps = float(payload.get("measured_fps") or 0)
    min_fps = float(payload.get("min_fps") or 0)
    required_fps = required_min_fps if required_min_fps is not None else min_fps
    device = str(payload.get("device") or "unknown")
    ok = (
        passed and frames_processed > 0 and min_fps >= required_fps and measured_fps >= required_fps
    )
    return ProductionCheck(
        "vision_benchmark",
        ok,
        (
            f"passed={passed}, fps={measured_fps:.2f}/{min_fps:.2f}, "
            f"required={required_fps:.2f}, "
            f"frames={frames_processed}, device={device}"
        ),
    )


def _check_vision_eval_report(path: Path) -> ProductionCheck:
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
    invalid_images = int(payload.get("invalid_images") or 0)
    ok = (
        passed
        and recall >= min_recall
        and false_positive_per_hour <= max_false_positive_per_hour
        and evaluated_hours > 0
        and frames_evaluated > 0
        and invalid_images == 0
    )
    return ProductionCheck(
        "vision_eval",
        ok,
        (
            f"passed={passed}, recall={recall:.3f}/{min_recall:.3f}, "
            f"fp_per_hour={false_positive_per_hour:.2f}/{max_false_positive_per_hour:.2f}, "
            f"hours={evaluated_hours:.1f}, frames={frames_evaluated}, invalid={invalid_images}"
        ),
    )


def _check_burn_in_report(
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
    duration_hours = float(payload.get("duration_seconds") or 0) / 3600
    camera_failures = int(payload.get("camera_failures") or 0)
    network_failures = int(payload.get("network_failures") or 0)
    battery_critical = bool(payload.get("battery_critical_seen"))
    thermal_critical = bool(payload.get("thermal_critical_seen"))
    charging_seen = bool(payload.get("charging_seen"))
    discharging_seen = bool(payload.get("discharging_seen"))
    charging_ok = charging_seen if require_charging_seen else True
    ok = (
        passed
        and duration_hours >= min_burn_in_hours
        and camera_failures == 0
        and network_failures == 0
        and not battery_critical
        and not thermal_critical
        and charging_ok
    )
    return ProductionCheck(
        "burn_in",
        ok,
        (
            f"passed={passed}, duration={duration_hours:.1f}h/{min_burn_in_hours:.1f}h, "
            f"camera_failures={camera_failures}, network_failures={network_failures}, "
            f"battery_critical={battery_critical}, thermal_critical={thermal_critical}, "
            f"charging_seen={charging_seen}, discharging_seen={discharging_seen}"
        ),
    )


_BLOCKING_RUNTIME_EVENTS = {
    "battery_critical",
    "disk_low",
    "network_offline",
    "notification_failed",
    "payment_skipped_battery_critical",
    "payment_skipped_no_position",
    "payment_skipped_offline",
    "service_crashed",
    "thermal_critical",
}


def _check_runtime_event_log(event_log_path: Path, burn_in_report_path: Path) -> ProductionCheck:
    if not event_log_path.exists():
        return ProductionCheck("runtime_event_log", True, f"missing optional {event_log_path}")
    if not event_log_path.is_file():
        return ProductionCheck("runtime_event_log", True, f"not a file: {event_log_path}")
    started_at = _burn_in_started_at(burn_in_report_path)
    failures: list[str] = []
    scanned = 0
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
        if name in _BLOCKING_RUNTIME_EVENTS:
            failures.append(f"{name}@line{line_number}")
        elif name == "network_recovery_attempted" and event.get("ok") is False:
            failures.append(f"network_recovery_failed@line{line_number}")

    return ProductionCheck(
        "runtime_event_log",
        not failures,
        (
            f"scanned={scanned}, since={started_at.isoformat() if started_at else '-'}, "
            f"failures={', '.join(failures) if failures else '-'}"
        ),
    )


def _burn_in_started_at(path: Path) -> datetime | None:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return _parse_timestamp(payload.get("started_at"))


def _check_report_freshness(
    env: Mapping[str, str],
    *,
    now: datetime,
    vision_eval_report_path: Path,
    benchmark_report_path: Path,
    autopay_smoke_report_path: Path,
    notification_report_path: Path,
    burn_in_report_path: Path,
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
    for key in ("tested_at", "generated_at", "ended_at"):
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


def _json_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
