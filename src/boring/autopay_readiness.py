"""Audit local de readiness autopaiement avant passage en mode reel."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class AutopayCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class AutopayReadinessReport:
    checks: list[AutopayCheck]

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def audit_autopay_readiness(
    *,
    env: Mapping[str, str] | None = None,
    endpoints_path: Path = Path("scripts/paybyphone_endpoints.json"),
    require_real_payment: bool = True,
) -> AutopayReadinessReport:
    values = env or os.environ
    checks = [
        _check_payment_mode(values),
        _check_provider(values),
        _check_dry_run(values, require_real_payment=require_real_payment),
        _check_plate(values),
        _check_duration_and_cooldown(values),
        _check_payment_limits(values),
        _check_paybyphone_credentials(values),
        _check_paybyphone_hints(values),
        _check_geofence(values),
        _check_har_artifact(endpoints_path),
    ]
    return AutopayReadinessReport(checks)


def write_report(report: AutopayReadinessReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _check_payment_mode(env: Mapping[str, str]) -> AutopayCheck:
    mode = _get(env, "PAYMENT_MODE", "assisted").lower()
    return AutopayCheck("payment_mode", mode == "auto", f"PAYMENT_MODE={mode}")


def _check_provider(env: Mapping[str, str]) -> AutopayCheck:
    provider = _get(env, "PAYMENT_PROVIDER", "paybyphone").lower()
    return AutopayCheck("payment_provider", provider == "paybyphone", f"provider={provider}")


def _check_dry_run(env: Mapping[str, str], *, require_real_payment: bool) -> AutopayCheck:
    dry_run = _env_bool(env, "PAYMENT_DRY_RUN", True)
    if require_real_payment:
        return AutopayCheck("payment_dry_run", not dry_run, f"PAYMENT_DRY_RUN={dry_run}")
    return AutopayCheck("payment_dry_run", True, f"PAYMENT_DRY_RUN={dry_run}")


def _check_plate(env: Mapping[str, str]) -> AutopayCheck:
    plate = _get(env, "DEFAULT_VEHICLE_PLATE", "AA-000-AA")
    ok = bool(plate.strip()) and plate != "AA-000-AA"
    return AutopayCheck("vehicle_plate", ok, _redact_plate(plate) if ok else "default/missing")


def _check_duration_and_cooldown(env: Mapping[str, str]) -> AutopayCheck:
    duration = _env_int(env, "DEFAULT_DURATION_MINUTES", 15)
    cooldown = _env_int(env, "COOLDOWN_MINUTES", 10)
    ok = 1 <= duration <= 60 and cooldown >= duration
    return AutopayCheck(
        "duration_cooldown",
        ok,
        f"duration={duration}min, cooldown={cooldown}min",
    )


def _check_payment_limits(env: Mapping[str, str]) -> AutopayCheck:
    max_session = _env_int(env, "MAX_SESSION_AMOUNT_CENTS", 500)
    max_daily = _env_int(env, "MAX_DAILY_AMOUNT_CENTS", 1500)
    ok = 1 <= max_session <= max_daily <= 10_000
    return AutopayCheck(
        "payment_limits",
        ok,
        f"session={max_session / 100:.2f} EUR, daily={max_daily / 100:.2f} EUR",
    )


def _check_paybyphone_credentials(env: Mapping[str, str]) -> AutopayCheck:
    required = ["PAYBYPHONE_USERNAME", "PAYBYPHONE_PASSWORD"]
    missing = [name for name in required if not _get(env, name, "").strip()]
    return AutopayCheck(
        "paybyphone_credentials",
        not missing,
        "ok" if not missing else f"missing {', '.join(missing)}",
    )


def _check_paybyphone_hints(env: Mapping[str, str]) -> AutopayCheck:
    required = [
        "PAYBYPHONE_API_BASE",
        "PAYBYPHONE_AUTH_URL",
        "PAYBYPHONE_CLIENT_ID",
        "PAYBYPHONE_RATE_OPTION_ID",
        "PAYBYPHONE_PAYMENT_METHOD_ID",
    ]
    missing = [name for name in required if not _get(env, name, "").strip()]
    return AutopayCheck(
        "paybyphone_har_hints",
        not missing,
        "ok" if not missing else f"missing {', '.join(missing)}",
    )


def _check_geofence(env: Mapping[str, str]) -> AutopayCheck:
    require_geofence = _env_bool(env, "BOX_REQUIRE_GEOFENCE", True)
    position_mode = _get(env, "POSITION_MODE", "static").lower()
    has_static_position = bool(_get(env, "BOX_LAT", "").strip()) and bool(
        _get(env, "BOX_LON", "").strip()
    )
    gpsd_ready = position_mode == "gpsd" and bool(_get(env, "GPSD_HOST", "").strip())
    ok = not require_geofence or has_static_position or gpsd_ready
    return AutopayCheck(
        "geofence_position",
        ok,
        (
            f"require={require_geofence}, mode={position_mode}, "
            f"static={has_static_position}, gpsd={gpsd_ready}"
        ),
    )


def _check_har_artifact(path: Path) -> AutopayCheck:
    if not path.exists():
        return AutopayCheck("paybyphone_har_artifact", False, f"missing {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return AutopayCheck("paybyphone_har_artifact", False, f"invalid json {path}")
    hints = payload.get("config_hints")
    flow_summary = payload.get("flow_summary")
    required_flow = [
        "auth",
        "location_lookup",
        "session_start",
        "active_session_check",
        "session_stop",
    ]
    missing_flow = [
        name
        for name in required_flow
        if not isinstance(flow_summary, dict) or not flow_summary.get(name)
    ]
    ok = isinstance(hints, dict) and any(value for value in hints.values()) and not missing_flow
    return AutopayCheck(
        "paybyphone_har_artifact",
        ok,
        (
            "config_hints + critical flow present"
            if ok
            else f"missing config_hints or flow: {', '.join(missing_flow) or 'config_hints'}"
        ),
    )


def _get(env: Mapping[str, str], name: str, default: str = "") -> str:
    return env.get(name, default)


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _redact_plate(plate: str) -> str:
    stripped = plate.strip()
    if len(stripped) <= 4:
        return "***"
    return stripped[:2] + "***" + stripped[-2:]
