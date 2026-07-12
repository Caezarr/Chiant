"""Pack de preuves terrain pour une Boring Box."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from boring.hardware_profile import audit_hardware_profile
from boring.runtime_events import BLOCKING_RUNTIME_EVENTS

REQUIRED_BOX_READY_CHECKS = {
    "autopay",
    "autopay_smoke",
    "burn_in",
    "burn_in_samples",
    "camera_runtime",
    "disk_space",
    "hardware",
    "hardware_env_consistency",
    "network_recovery",
    "network_runtime",
    "notification_test",
    "notification_webhook",
    "position_runtime",
    "power_budget",
    "power_runtime",
    "report_freshness",
    "runtime_event_log",
    "systemd_runtime",
    "systemd_service",
    "vision",
    "vision_benchmark",
    "vision_eval",
}

RUNTIME_REPORTS = {
    "burn_in",
    "camera_runtime",
    "network_runtime",
    "position_runtime",
    "power_runtime",
    "systemd_runtime",
}


@dataclass(frozen=True)
class EvidenceItem:
    name: str
    path: str
    present: bool
    valid_json: bool
    passed: bool | None
    size_bytes: int | None
    sha256: str | None
    format: str
    detail: str


@dataclass(frozen=True)
class EvidencePack:
    generated_at: str
    items: list[EvidenceItem]

    @property
    def passed(self) -> bool:
        return all(evidence_item_ok(item) for item in self.items)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def build_evidence_pack(paths: dict[str, Path]) -> EvidencePack:
    return EvidencePack(
        generated_at=datetime.now(timezone.utc).isoformat(),
        items=[_read_item(name, path) for name, path in paths.items()],
    )


def write_pack(pack: EvidencePack, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n")


def default_evidence_paths() -> dict[str, Path]:
    return {
        "box_ready": Path("reports/box-readiness.json"),
        "hardware_profile": Path("deploy/pi/hardware-profile.json"),
        "systemd_runtime": Path("reports/systemd-check.json"),
        "position_runtime": Path("reports/position-check.json"),
        "camera_runtime": Path("reports/camera-check.json"),
        "network_runtime": Path("reports/network-check.json"),
        "power_runtime": Path("reports/power-check.json"),
        "runtime_events": Path("/var/lib/boring/events.jsonl"),
        "vision_eval": Path("reports/vision-eval.json"),
        "vision_benchmark": Path("reports/vision-benchmark.json"),
        "paybyphone_endpoints": Path("scripts/paybyphone_endpoints.json"),
        "autopay_smoke": Path("reports/autopay-smoke.json"),
        "notification_test": Path("reports/notification-test.json"),
        "burn_in": Path("burn-in/report.json"),
        "burn_in_samples": Path("burn-in/samples.jsonl"),
    }


def evidence_item_ok(item: EvidenceItem) -> bool:
    if not item.present or not item.valid_json:
        return False
    if item.name in {
        "autopay_smoke",
        "box_ready",
        "burn_in_samples",
        "hardware_profile",
        "notification_test",
        "paybyphone_endpoints",
        "runtime_events",
        "vision_benchmark",
        "vision_eval",
    }:
        return item.passed is True
    return item.passed is True


def _read_item(name: str, path: Path) -> EvidenceItem:
    if not path.exists():
        return EvidenceItem(
            name, str(path), False, False, None, None, None, _format(name), "missing"
        )
    raw = path.read_bytes()
    if name == "autopay_smoke":
        return _read_autopay_smoke(name, path, raw)
    if name == "box_ready":
        return _read_box_ready(name, path, raw)
    if name == "burn_in_samples":
        return _read_burn_in_samples(name, path, raw)
    if name == "hardware_profile":
        return _read_hardware_profile(name, path, raw)
    if name == "notification_test":
        return _read_notification_test(name, path, raw)
    if name == "paybyphone_endpoints":
        return _read_paybyphone_endpoints(name, path, raw)
    if name == "runtime_events":
        return _read_runtime_events(name, path, raw)
    if name in RUNTIME_REPORTS:
        return _read_runtime_report(name, path, raw)
    if name == "vision_benchmark":
        return _read_vision_benchmark(name, path, raw)
    if name == "vision_eval":
        return _read_vision_eval(name, path, raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    passed = payload.get("passed") if isinstance(payload, dict) else None
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=passed if isinstance(passed, bool) else None,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=_detail(payload),
    )


def _read_runtime_report(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    if not isinstance(payload, dict):
        return EvidenceItem(
            name=name,
            path=str(path),
            present=True,
            valid_json=True,
            passed=False,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            format=_format(name),
            detail="json is not an object",
        )

    failures = _runtime_report_failures(name, payload)
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=not failures,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"passed={payload.get('passed') is True}, "
            f"failures={','.join(failures) if failures else '-'}"
        ),
    )


def _runtime_report_failures(name: str, payload: dict) -> list[str]:
    failures = []
    if payload.get("passed") is not True:
        failures.append("passed")
    if name != "burn_in" and payload.get("failures") != []:
        failures.append("failures")

    if name == "burn_in":
        return failures + _burn_in_report_failures(payload)
    if name == "camera_runtime":
        return failures + _camera_report_failures(payload)
    if name == "network_runtime":
        return failures + _network_report_failures(payload)
    if name == "position_runtime":
        return failures + _position_report_failures(payload)
    if name == "power_runtime":
        return failures + _power_report_failures(payload)
    if name == "systemd_runtime":
        return failures + _systemd_report_failures(payload)
    return failures


def _burn_in_report_failures(payload: dict) -> list[str]:
    failures = []
    duration = _number(payload.get("duration_seconds"))
    sample_count = _integer(payload.get("sample_count"))
    if duration is None or duration <= 0:
        failures.append("duration")
    if sample_count is None or sample_count <= 0:
        failures.append("sample_count")
    if payload.get("camera_failures") != 0:
        failures.append("camera_failures")
    if payload.get("network_failures") != 0:
        failures.append("network_failures")
    if not isinstance(payload.get("min_battery_percent"), int):
        failures.append("min_battery")
    if not isinstance(payload.get("max_temp_c"), (int, float)):
        failures.append("max_temp")
    if payload.get("charging_seen") is not True:
        failures.append("charging_seen")
    if payload.get("discharging_seen") is not True:
        failures.append("discharging_seen")
    if payload.get("battery_critical_seen") is True:
        failures.append("battery_critical")
    if payload.get("thermal_critical_seen") is True:
        failures.append("thermal_critical")
    return failures


def _camera_report_failures(payload: dict) -> list[str]:
    failures = []
    width = _integer(payload.get("width"))
    height = _integer(payload.get("height"))
    min_width = _integer(payload.get("min_width"))
    min_height = _integer(payload.get("min_height"))
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if width is None or min_width is None or width < min_width:
        failures.append("width")
    if height is None or min_height is None or height < min_height:
        failures.append("height")
    return failures


def _network_report_failures(payload: dict) -> list[str]:
    failures = []
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if not _has_text(payload.get("target")):
        failures.append("target")
    if payload.get("online") is not True:
        failures.append("online")
    if payload.get("recovery_command_configured") is not True:
        failures.append("recovery")
    return failures


def _position_report_failures(payload: dict) -> list[str]:
    failures = []
    mode = str(payload.get("mode") or "")
    source = str(payload.get("source") or "")
    lat = _number(payload.get("lat"))
    lon = _number(payload.get("lon"))
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if mode not in {"static", "gpsd"}:
        failures.append("mode")
    if source != mode:
        failures.append("source")
    if lat is None or not -90 <= lat <= 90:
        failures.append("lat")
    if lon is None or not -180 <= lon <= 180:
        failures.append("lon")
    return failures


def _power_report_failures(payload: dict) -> list[str]:
    failures = []
    battery_percent = _integer(payload.get("battery_percent"))
    estimated_runtime_hours = _number(payload.get("estimated_runtime_hours"))
    required_runtime_hours = _number(payload.get("required_runtime_hours"))
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if battery_percent is None or battery_percent <= 0:
        failures.append("battery_percent")
    if not isinstance(payload.get("charging"), bool):
        failures.append("charging")
    if not _has_text(payload.get("source")):
        failures.append("source")
    if _number(payload.get("battery_capacity_wh")) is None:
        failures.append("battery_capacity")
    if (
        estimated_runtime_hours is None
        or required_runtime_hours is None
        or estimated_runtime_hours < required_runtime_hours
    ):
        failures.append("runtime")
    return failures


def _systemd_report_failures(payload: dict) -> list[str]:
    failures = []
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if payload.get("enabled_state") != "enabled":
        failures.append("enabled")
    if payload.get("active_state") != "active":
        failures.append("active")
    if payload.get("sub_state") != "running":
        failures.append("sub")
    if payload.get("unit_file_state") != "enabled":
        failures.append("unit_file")
    if payload.get("type") != "notify":
        failures.append("type")
    watchdog_usec = _integer(payload.get("watchdog_usec"))
    if watchdog_usec is None or watchdog_usec <= 0:
        failures.append("watchdog")
    if "boring box-run" not in str(payload.get("exec_start") or ""):
        failures.append("exec_start")
    if payload.get("user") != "boring":
        failures.append("user")
    return failures


def _read_box_ready(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    if not isinstance(payload, dict):
        return EvidenceItem(
            name=name,
            path=str(path),
            present=True,
            valid_json=True,
            passed=False,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            format=_format(name),
            detail="json is not an object",
        )

    checks = payload.get("checks")
    if not isinstance(checks, list):
        return EvidenceItem(
            name=name,
            path=str(path),
            present=True,
            valid_json=True,
            passed=False,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            format=_format(name),
            detail="checks=missing",
        )

    check_status: dict[str, bool] = {}
    malformed = 0
    for check in checks:
        if not isinstance(check, dict):
            malformed += 1
            continue
        check_name = check.get("name")
        ok = check.get("ok")
        if not isinstance(check_name, str) or not isinstance(ok, bool):
            malformed += 1
            continue
        check_status[check_name] = ok

    missing = sorted(REQUIRED_BOX_READY_CHECKS - set(check_status))
    failed = sorted(name for name in REQUIRED_BOX_READY_CHECKS if check_status.get(name) is False)
    passed = payload.get("passed") is True and not missing and not failed and malformed == 0
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=passed,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"passed={payload.get('passed') is True}, checks={len(check_status)}, "
            f"missing={','.join(missing) if missing else '-'}, "
            f"failed={','.join(failed) if failed else '-'}, malformed={malformed}"
        ),
    )


def _read_hardware_profile(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    if not isinstance(payload, dict):
        return EvidenceItem(
            name=name,
            path=str(path),
            present=True,
            valid_json=True,
            passed=False,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            format=_format(name),
            detail="json is not an object",
        )

    report = audit_hardware_profile(path)
    failed = [check.name for check in report.checks if not check.ok]
    board = payload.get("board") or {}
    power = payload.get("power") or {}
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=report.passed,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"preset={payload.get('preset_id') or '-'}, "
            f"board={board.get('model') or '-'}, "
            f"battery={power.get('battery_capacity_wh') or '-'}Wh, "
            f"vehicle_charge={power.get('vehicle_charge_watts') or '-'}W, "
            f"checks={','.join(failed) if failed else 'ok'}"
        ),
    )


def _read_runtime_events(name: str, path: Path, raw: bytes) -> EvidenceItem:
    invalid_lines = 0
    scanned = 0
    heartbeat_seen = False
    blocking: list[str] = []
    for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(payload, dict):
            invalid_lines += 1
            continue
        scanned += 1
        event = payload.get("event")
        if event == "heartbeat":
            heartbeat_seen = True
        if event in BLOCKING_RUNTIME_EVENTS:
            blocking.append(f"{event}@line{line_number}")
        if event == "network_recovery_attempted" and payload.get("ok") is False:
            blocking.append(f"network_recovery_failed@line{line_number}")

    passed = invalid_lines == 0 and scanned > 0 and heartbeat_seen and not blocking
    blocking_detail = ",".join(blocking) if blocking else "-"
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=invalid_lines == 0,
        passed=passed,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"scanned={scanned}, heartbeat={heartbeat_seen}, "
            f"invalid_lines={invalid_lines}, blocking={blocking_detail}"
        ),
    )


def _read_burn_in_samples(name: str, path: Path, raw: bytes) -> EvidenceItem:
    invalid_lines = 0
    scanned = 0
    camera_failures = 0
    network_failures = 0
    battery_samples = 0
    temp_samples = 0
    for line_number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(payload, dict):
            invalid_lines += 1
            continue
        scanned += 1
        if payload.get("camera_ok") is not True:
            camera_failures += 1
        if payload.get("network_online") is not True:
            network_failures += 1
        if payload.get("battery_percent") is not None:
            battery_samples += 1
        if payload.get("temp_c") is not None:
            temp_samples += 1

    passed = (
        invalid_lines == 0
        and scanned > 0
        and camera_failures == 0
        and network_failures == 0
        and battery_samples > 0
        and temp_samples > 0
    )
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=invalid_lines == 0,
        passed=passed,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"scanned={scanned}, camera_failures={camera_failures}, "
            f"network_failures={network_failures}, battery_samples={battery_samples}, "
            f"temp_samples={temp_samples}, invalid_lines={invalid_lines}"
        ),
    )


def _read_paybyphone_endpoints(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    hints = payload.get("config_hints") if isinstance(payload, dict) else None
    flow = payload.get("flow_summary") if isinstance(payload, dict) else None
    required_hints = [
        "base_url",
        "auth_url",
        "client_id",
        "rate_option_id",
        "payment_method_id",
    ]
    required_flow = [
        "auth",
        "location_lookup",
        "session_start",
        "active_session_check",
        "session_stop",
    ]
    missing_hints = [
        key for key in required_hints if not isinstance(hints, dict) or not hints.get(key)
    ]
    missing_flow = [key for key in required_flow if not isinstance(flow, dict) or not flow.get(key)]
    passed = not missing_hints and not missing_flow
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=passed,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"missing_hints={','.join(missing_hints) if missing_hints else '-'}, "
            f"missing_flow={','.join(missing_flow) if missing_flow else '-'}"
        ),
    )


def _read_autopay_smoke(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    passed = payload.get("passed") is True if isinstance(payload, dict) else False
    dry_run = payload.get("dry_run") is True if isinstance(payload, dict) else True
    amount_cents = payload.get("amount_cents") if isinstance(payload, dict) else None
    amount_ok = isinstance(amount_cents, int) and amount_cents > 0
    active_verified = (
        payload.get("active_session_verified") is True if isinstance(payload, dict) else False
    )
    stopped = payload.get("stopped") is True if isinstance(payload, dict) else False
    stop_verified = payload.get("stop_verified") is True if isinstance(payload, dict) else False
    provider = payload.get("provider") if isinstance(payload, dict) else None
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    zone_id = payload.get("zone_id") if isinstance(payload, dict) else None
    complete = (
        passed
        and not dry_run
        and amount_ok
        and active_verified
        and stopped
        and stop_verified
        and bool(provider)
        and bool(session_id)
        and bool(zone_id)
    )
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=complete,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"passed={passed}, dry_run={dry_run}, amount={amount_cents}, "
            f"active={active_verified}, stopped={stopped}, stop_verified={stop_verified}, "
            f"provider={'ok' if provider else 'missing'}, "
            f"session={'ok' if session_id else 'missing'}, zone={'ok' if zone_id else 'missing'}"
        ),
    )


def _read_notification_test(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    passed = payload.get("passed") is True if isinstance(payload, dict) else False
    status_code = payload.get("status_code") if isinstance(payload, dict) else None
    webhook_host = str(payload.get("webhook_host") or "") if isinstance(payload, dict) else ""
    title = str(payload.get("title") or "") if isinstance(payload, dict) else ""
    message = str(payload.get("message") or "") if isinstance(payload, dict) else ""
    status_ok = isinstance(status_code, int) and 200 <= status_code < 300
    complete = passed and status_ok and bool(webhook_host) and bool(title) and bool(message)
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=complete,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"passed={passed}, status={status_code}, "
            f"host={'ok' if webhook_host else 'missing'}, "
            f"title={'ok' if title else 'missing'}, message={'ok' if message else 'missing'}"
        ),
    )


def _read_vision_eval(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    passed = payload.get("passed") is True if isinstance(payload, dict) else False
    recall = _number(payload.get("recall")) if isinstance(payload, dict) else None
    min_recall = _number(payload.get("min_recall")) if isinstance(payload, dict) else None
    false_positive_per_hour = (
        _number(payload.get("false_positive_per_hour")) if isinstance(payload, dict) else None
    )
    max_false_positive_per_hour = (
        _number(payload.get("max_false_positive_per_hour")) if isinstance(payload, dict) else None
    )
    evaluated_hours = _number(payload.get("evaluated_hours")) if isinstance(payload, dict) else None
    frames_evaluated = (
        _integer(payload.get("frames_evaluated")) if isinstance(payload, dict) else None
    )
    invalid_images = _integer(payload.get("invalid_images")) if isinstance(payload, dict) else None
    model_path = str(payload.get("model_path") or "") if isinstance(payload, dict) else ""
    dataset_path = str(payload.get("dataset_path") or "") if isinstance(payload, dict) else ""
    ok = (
        passed
        and recall is not None
        and min_recall is not None
        and recall >= min_recall
        and false_positive_per_hour is not None
        and max_false_positive_per_hour is not None
        and false_positive_per_hour <= max_false_positive_per_hour
        and evaluated_hours is not None
        and evaluated_hours > 0
        and frames_evaluated is not None
        and frames_evaluated > 0
        and invalid_images == 0
        and bool(model_path)
        and bool(dataset_path)
    )
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=ok,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"passed={passed}, recall={_fmt(recall)}/{_fmt(min_recall)}, "
            f"fp_per_hour={_fmt(false_positive_per_hour)}/{_fmt(max_false_positive_per_hour)}, "
            f"hours={_fmt(evaluated_hours)}, frames={frames_evaluated}, "
            f"invalid={invalid_images}, model={'ok' if model_path else 'missing'}, "
            f"dataset={'ok' if dataset_path else 'missing'}"
        ),
    )


def _read_vision_benchmark(name: str, path: Path, raw: bytes) -> EvidenceItem:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            _format(name),
            "invalid json",
        )
    passed = payload.get("passed") is True if isinstance(payload, dict) else False
    frames_processed = (
        _integer(payload.get("frames_processed")) if isinstance(payload, dict) else None
    )
    measured_fps = _number(payload.get("measured_fps")) if isinstance(payload, dict) else None
    min_fps = _number(payload.get("min_fps")) if isinstance(payload, dict) else None
    model_path = str(payload.get("model_path") or "") if isinstance(payload, dict) else ""
    device = str(payload.get("device") or "") if isinstance(payload, dict) else ""
    ok = (
        passed
        and frames_processed is not None
        and frames_processed > 0
        and measured_fps is not None
        and min_fps is not None
        and measured_fps >= min_fps
        and bool(model_path)
        and bool(device)
    )
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=ok,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        format=_format(name),
        detail=(
            f"passed={passed}, fps={_fmt(measured_fps)}/{_fmt(min_fps)}, "
            f"frames={frames_processed}, model={'ok' if model_path else 'missing'}, "
            f"device={'ok' if device else 'missing'}"
        ),
    )


def _detail(payload) -> str:
    if not isinstance(payload, dict):
        return "json is not an object"
    if "passed" in payload:
        return f"passed={payload.get('passed')}"
    return "json present"


def _format(name: str) -> str:
    if name in {"burn_in_samples", "runtime_events"}:
        return "jsonl"
    return "json"


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"
