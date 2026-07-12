"""Pack de preuves terrain pour une Boring Box."""

from __future__ import annotations

import hashlib
import json
import os
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

FRESHNESS_REPORTS = (
    "box_ready",
    "systemd_runtime",
    "position_runtime",
    "camera_runtime",
    "network_runtime",
    "power_runtime",
    "vision_eval",
    "vision_benchmark",
    "autopay_smoke",
    "notification_test",
    "burn_in",
)


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


def build_evidence_pack(
    paths: dict[str, Path],
    *,
    max_report_age_hours: float | None = None,
    now: datetime | None = None,
) -> EvidencePack:
    items = [
        _read_item(
            name,
            path,
            burn_in_report_path=paths.get("burn_in") if name == "burn_in_samples" else None,
        )
        for name, path in paths.items()
    ]
    if "burn_in" in paths and "runtime_events" in paths:
        items.append(_read_runtime_alignment(paths["burn_in"], paths["runtime_events"]))
    if "hardware_profile" in paths and "vision_benchmark" in paths:
        items.append(
            _read_hardware_benchmark_alignment(
                paths["hardware_profile"],
                paths["vision_benchmark"],
            )
        )
    if "vision_eval" in paths and "vision_benchmark" in paths:
        items.append(_read_vision_model_alignment(paths["vision_eval"], paths["vision_benchmark"]))
        items.append(
            _read_vision_artifact_alignment(paths["vision_eval"], paths["vision_benchmark"])
        )
    if "autopay_smoke" in paths and "paybyphone_endpoints" in paths:
        items.append(
            _read_autopay_provider_alignment(
                paths["autopay_smoke"],
                paths["paybyphone_endpoints"],
            )
        )
    if max_report_age_hours is not None:
        items.append(
            _read_report_freshness(
                paths,
                max_age_hours=max_report_age_hours,
                now=now or datetime.now(timezone.utc),
            )
        )
    return EvidencePack(
        generated_at=datetime.now(timezone.utc).isoformat(),
        items=items,
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
        "runtime_events": Path(os.getenv("BOX_EVENT_LOG_PATH", "/var/lib/boring/events.jsonl")),
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


def _read_item(
    name: str,
    path: Path,
    *,
    burn_in_report_path: Path | None = None,
) -> EvidenceItem:
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
        return _read_burn_in_samples(name, path, raw, report_path=burn_in_report_path)
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


def _read_runtime_alignment(
    burn_in_path: Path,
    runtime_events_path: Path,
    *,
    max_heartbeat_gap_seconds: float = 1800.0,
) -> EvidenceItem:
    path = f"{burn_in_path} + {runtime_events_path}"
    if not burn_in_path.exists() or not runtime_events_path.exists():
        missing = [
            str(missing_path)
            for missing_path in (burn_in_path, runtime_events_path)
            if not missing_path.exists()
        ]
        return EvidenceItem(
            "runtime_alignment",
            path,
            False,
            False,
            None,
            None,
            None,
            _format("runtime_alignment"),
            f"missing {', '.join(missing)}",
        )

    try:
        burn_in = json.loads(burn_in_path.read_text())
    except json.JSONDecodeError:
        return EvidenceItem(
            "runtime_alignment",
            path,
            True,
            False,
            None,
            None,
            None,
            _format("runtime_alignment"),
            f"invalid json {burn_in_path}",
        )
    if not isinstance(burn_in, dict):
        return EvidenceItem(
            "runtime_alignment",
            path,
            True,
            True,
            False,
            None,
            None,
            _format("runtime_alignment"),
            "burn_in=json is not an object",
        )

    started_at = _parse_evidence_timestamp(burn_in.get("started_at"))
    ended_at = _parse_evidence_timestamp(burn_in.get("ended_at"))
    invalid_lines = 0
    scanned = 0
    earliest_heartbeat: datetime | None = None
    latest_heartbeat: datetime | None = None
    blocking: list[str] = []
    for line_number, line in enumerate(
        runtime_events_path.read_text().splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines += 1
            continue
        if not isinstance(event, dict):
            invalid_lines += 1
            continue
        timestamp = _parse_evidence_timestamp(event.get("ts"))
        if started_at is not None and timestamp is not None and timestamp < started_at:
            continue
        scanned += 1
        name = event.get("event")
        if name == "heartbeat" and timestamp is not None:
            if earliest_heartbeat is None or timestamp < earliest_heartbeat:
                earliest_heartbeat = timestamp
            if latest_heartbeat is None or timestamp > latest_heartbeat:
                latest_heartbeat = timestamp
        if name in BLOCKING_RUNTIME_EVENTS:
            blocking.append(f"{name}@line{line_number}")
        elif name == "network_recovery_attempted" and event.get("ok") is False:
            blocking.append(f"network_recovery_failed@line{line_number}")

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
    passed = (
        started_at is not None
        and ended_at is not None
        and invalid_lines == 0
        and scanned > 0
        and heartbeat_start_gap_seconds is not None
        and heartbeat_end_gap_seconds is not None
        and heartbeat_start_gap_seconds <= max_heartbeat_gap_seconds
        and heartbeat_end_gap_seconds <= max_heartbeat_gap_seconds
        and not blocking
    )
    raw = burn_in_path.read_bytes() + runtime_events_path.read_bytes()
    return EvidenceItem(
        "runtime_alignment",
        path,
        True,
        invalid_lines == 0,
        passed,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        _format("runtime_alignment"),
        (
            f"scanned={scanned}, since={started_at.isoformat() if started_at else '-'}, "
            f"heartbeat_start_gap={_fmt_seconds(heartbeat_start_gap_seconds)}/"
            f"{max_heartbeat_gap_seconds:.0f}s, "
            f"heartbeat_end_gap={_fmt_seconds(heartbeat_end_gap_seconds)}/"
            f"{max_heartbeat_gap_seconds:.0f}s, "
            f"blocking={','.join(blocking) if blocking else '-'}, "
            f"invalid_lines={invalid_lines}"
        ),
    )


def _read_hardware_benchmark_alignment(
    hardware_profile_path: Path,
    benchmark_path: Path,
) -> EvidenceItem:
    path = f"{hardware_profile_path} + {benchmark_path}"
    if not hardware_profile_path.exists() or not benchmark_path.exists():
        missing = [
            str(missing_path)
            for missing_path in (hardware_profile_path, benchmark_path)
            if not missing_path.exists()
        ]
        return EvidenceItem(
            "hardware_benchmark_alignment",
            path,
            False,
            False,
            None,
            None,
            None,
            _format("hardware_benchmark_alignment"),
            f"missing {', '.join(missing)}",
        )

    try:
        hardware = json.loads(hardware_profile_path.read_text())
        benchmark = json.loads(benchmark_path.read_text())
    except json.JSONDecodeError as exc:
        return EvidenceItem(
            "hardware_benchmark_alignment",
            path,
            True,
            False,
            None,
            None,
            None,
            _format("hardware_benchmark_alignment"),
            f"invalid json {exc}",
        )
    if not isinstance(hardware, dict) or not isinstance(benchmark, dict):
        return EvidenceItem(
            "hardware_benchmark_alignment",
            path,
            True,
            True,
            False,
            None,
            None,
            _format("hardware_benchmark_alignment"),
            "json is not an object",
        )

    runtime = hardware.get("runtime") if isinstance(hardware.get("runtime"), dict) else {}
    required_fps = _number(runtime.get("min_benchmark_fps"))
    measured_fps = _number(benchmark.get("measured_fps"))
    benchmark_min_fps = _number(benchmark.get("min_fps"))
    benchmark_passed = benchmark.get("passed") is True
    passed = (
        benchmark_passed
        and required_fps is not None
        and required_fps > 0
        and measured_fps is not None
        and benchmark_min_fps is not None
        and benchmark_min_fps >= required_fps
        and measured_fps >= required_fps
    )
    raw = hardware_profile_path.read_bytes() + benchmark_path.read_bytes()
    return EvidenceItem(
        "hardware_benchmark_alignment",
        path,
        True,
        True,
        passed,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        _format("hardware_benchmark_alignment"),
        (
            f"benchmark_passed={benchmark_passed}, "
            f"measured_fps={_fmt(measured_fps)}/{_fmt(required_fps)}, "
            f"benchmark_min_fps={_fmt(benchmark_min_fps)}/{_fmt(required_fps)}"
        ),
    )


def _read_vision_model_alignment(
    eval_path: Path,
    benchmark_path: Path,
) -> EvidenceItem:
    path = f"{eval_path} + {benchmark_path}"
    if not eval_path.exists() or not benchmark_path.exists():
        missing = [
            str(missing_path)
            for missing_path in (eval_path, benchmark_path)
            if not missing_path.exists()
        ]
        return EvidenceItem(
            "vision_model_alignment",
            path,
            False,
            False,
            None,
            None,
            None,
            _format("vision_model_alignment"),
            f"missing {', '.join(missing)}",
        )

    try:
        eval_payload = json.loads(eval_path.read_text())
        benchmark_payload = json.loads(benchmark_path.read_text())
    except json.JSONDecodeError as exc:
        return EvidenceItem(
            "vision_model_alignment",
            path,
            True,
            False,
            None,
            None,
            None,
            _format("vision_model_alignment"),
            f"invalid json {exc}",
        )
    if not isinstance(eval_payload, dict) or not isinstance(benchmark_payload, dict):
        return EvidenceItem(
            "vision_model_alignment",
            path,
            True,
            True,
            False,
            None,
            None,
            _format("vision_model_alignment"),
            "json is not an object",
        )

    eval_model = str(eval_payload.get("model_path") or "")
    benchmark_model = str(benchmark_payload.get("model_path") or "")
    passed = (
        bool(eval_model)
        and bool(benchmark_model)
        and _same_path(
            eval_model,
            benchmark_model,
        )
    )
    raw = eval_path.read_bytes() + benchmark_path.read_bytes()
    return EvidenceItem(
        "vision_model_alignment",
        path,
        True,
        True,
        passed,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        _format("vision_model_alignment"),
        (
            f"eval_model={eval_model or '-'}, "
            f"benchmark_model={benchmark_model or '-'}, "
            f"same_model={passed}"
        ),
    )


def _read_vision_artifact_alignment(
    eval_path: Path,
    benchmark_path: Path,
) -> EvidenceItem:
    path = f"{eval_path} + {benchmark_path}"
    if not eval_path.exists() or not benchmark_path.exists():
        missing = [
            str(missing_path)
            for missing_path in (eval_path, benchmark_path)
            if not missing_path.exists()
        ]
        return EvidenceItem(
            "vision_artifact_alignment",
            path,
            False,
            False,
            None,
            None,
            None,
            _format("vision_artifact_alignment"),
            f"missing {', '.join(missing)}",
        )

    try:
        eval_payload = json.loads(eval_path.read_text())
        benchmark_payload = json.loads(benchmark_path.read_text())
    except json.JSONDecodeError as exc:
        return EvidenceItem(
            "vision_artifact_alignment",
            path,
            True,
            False,
            None,
            None,
            None,
            _format("vision_artifact_alignment"),
            f"invalid json {exc}",
        )
    if not isinstance(eval_payload, dict) or not isinstance(benchmark_payload, dict):
        return EvidenceItem(
            "vision_artifact_alignment",
            path,
            True,
            True,
            False,
            None,
            None,
            _format("vision_artifact_alignment"),
            "json is not an object",
        )

    eval_model = str(eval_payload.get("model_path") or "")
    benchmark_model = str(benchmark_payload.get("model_path") or "")
    dataset = str(eval_payload.get("dataset_path") or "")
    model_exists = bool(eval_model) and _path_exists(eval_model)
    benchmark_model_exists = bool(benchmark_model) and _path_exists(benchmark_model)
    dataset_exists = bool(dataset) and _path_exists(dataset)
    data_yaml_exists = bool(dataset) and (Path(dataset).expanduser() / "data.yaml").exists()
    passed = model_exists and benchmark_model_exists and dataset_exists and data_yaml_exists
    raw = eval_path.read_bytes() + benchmark_path.read_bytes()
    return EvidenceItem(
        "vision_artifact_alignment",
        path,
        True,
        True,
        passed,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        _format("vision_artifact_alignment"),
        (
            f"eval_model={'ok' if model_exists else 'missing'}, "
            f"benchmark_model={'ok' if benchmark_model_exists else 'missing'}, "
            f"dataset={'ok' if dataset_exists else 'missing'}, "
            f"data_yaml={'ok' if data_yaml_exists else 'missing'}"
        ),
    )


def _read_report_freshness(
    paths: dict[str, Path],
    *,
    max_age_hours: float,
    now: datetime,
) -> EvidenceItem:
    if max_age_hours <= 0:
        return EvidenceItem(
            "report_freshness",
            "aggregate",
            True,
            True,
            True,
            None,
            None,
            _format("report_freshness"),
            "disabled",
        )

    failures: list[str] = []
    ages: list[str] = []
    raw_parts: list[bytes] = []
    for name in FRESHNESS_REPORTS:
        path = paths.get(name)
        if path is None:
            continue
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            failures.append(f"{name}=missing")
            continue
        raw_parts.append(raw)
        try:
            payload = json.loads(raw.decode("utf-8"))
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
        age_hours = (
            now.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)
        ).total_seconds() / 3600
        ages.append(f"{name}={age_hours:.1f}h")
        if age_hours < -0.1:
            failures.append(f"{name}=future_timestamp")
        elif age_hours > max_age_hours:
            failures.append(f"{name}={age_hours:.1f}h>{max_age_hours:.1f}h")

    raw = b"".join(raw_parts)
    return EvidenceItem(
        "report_freshness",
        "aggregate",
        True,
        not any("invalid_json" in failure for failure in failures),
        not failures,
        len(raw) if raw_parts else None,
        hashlib.sha256(raw).hexdigest() if raw_parts else None,
        _format("report_freshness"),
        (
            f"max_age={max_age_hours:.1f}h, "
            f"ages={', '.join(ages) if ages else '-'}, "
            f"failures={', '.join(failures) if failures else '-'}"
        ),
    )


def _report_timestamp(payload: dict) -> datetime | None:
    for key in ("checked_at", "tested_at", "generated_at", "ended_at"):
        timestamp = _parse_evidence_timestamp(payload.get(key))
        if timestamp is not None:
            return timestamp
    return None


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
    requested_duration = _number(payload.get("requested_duration_seconds"))
    interval_seconds = _number(payload.get("interval_seconds"))
    max_sample_gap_seconds = _number(payload.get("max_sample_gap_seconds"))
    sample_count = _integer(payload.get("sample_count"))
    if requested_duration is None or requested_duration <= 0:
        failures.append("requested_duration")
    if duration is None or duration <= 0:
        failures.append("duration")
    elif requested_duration is not None and duration + 1.0 < requested_duration:
        failures.append("duration_short")
    if interval_seconds is None or interval_seconds <= 0:
        failures.append("interval")
    if max_sample_gap_seconds is None or max_sample_gap_seconds <= 0:
        failures.append("max_sample_gap")
    elif interval_seconds is not None and max_sample_gap_seconds < interval_seconds:
        failures.append("max_sample_gap_lt_interval")
    if sample_count is None or sample_count <= 0:
        failures.append("sample_count")
    if payload.get("camera_failures") != 0:
        failures.append("camera_failures")
    if payload.get("network_failures") != 0:
        failures.append("network_failures")
    battery_low_percent = _integer(payload.get("battery_low_percent"))
    battery_critical_percent = _integer(payload.get("battery_critical_percent"))
    thermal_warning_c = _number(payload.get("thermal_warning_c"))
    thermal_critical_c = _number(payload.get("thermal_critical_c"))
    if battery_low_percent is None:
        failures.append("battery_low_percent")
    if battery_critical_percent is None:
        failures.append("battery_critical_percent")
    if thermal_warning_c is None:
        failures.append("thermal_warning_c")
    if thermal_critical_c is None:
        failures.append("thermal_critical_c")
    min_battery = _number(payload.get("min_battery_percent"))
    if min_battery is None:
        failures.append("min_battery")
    elif battery_low_percent is not None and min_battery <= battery_low_percent:
        failures.append("min_battery_low")
    if (
        min_battery is not None
        and battery_critical_percent is not None
        and min_battery <= battery_critical_percent
    ):
        failures.append("min_battery_critical")
    max_temp = _number(payload.get("max_temp_c"))
    if max_temp is None:
        failures.append("max_temp")
    elif thermal_critical_c is not None and max_temp >= thermal_critical_c:
        failures.append("max_temp_critical")
    if payload.get("charging_seen") is not True:
        failures.append("charging_seen")
    if payload.get("discharging_seen") is not True:
        failures.append("discharging_seen")
    if min_battery is not None and battery_low_percent is not None:
        expected_low_seen = min_battery <= battery_low_percent
        if payload.get("battery_low_seen") is not expected_low_seen:
            failures.append("battery_low_threshold_mismatch")
    if min_battery is not None and battery_critical_percent is not None:
        expected_critical_seen = min_battery <= battery_critical_percent
        if payload.get("battery_critical_seen") is not expected_critical_seen:
            failures.append("battery_critical_threshold_mismatch")
    if max_temp is not None and thermal_warning_c is not None:
        expected_warning_seen = max_temp >= thermal_warning_c
        if payload.get("thermal_warning_seen") is not expected_warning_seen:
            failures.append("thermal_warning_threshold_mismatch")
    if max_temp is not None and thermal_critical_c is not None:
        expected_critical_seen = max_temp >= thermal_critical_c
        if payload.get("thermal_critical_seen") is not expected_critical_seen:
            failures.append("thermal_critical_threshold_mismatch")
    if payload.get("battery_low_seen") is True:
        failures.append("battery_low")
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
    timeout_seconds = _number(payload.get("timeout_seconds"))
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if not _has_text(payload.get("target")):
        failures.append("target")
    if timeout_seconds is None or timeout_seconds <= 0:
        failures.append("timeout")
    if payload.get("online") is not True:
        failures.append("online")
    if payload.get("recovery_command_configured") is not True:
        failures.append("recovery")
    if not _has_text(payload.get("recovery_command")):
        failures.append("recovery_command")
    return failures


def _position_report_failures(payload: dict) -> list[str]:
    failures = []
    mode = str(payload.get("mode") or "")
    source = str(payload.get("source") or "")
    lat = _number(payload.get("lat"))
    lon = _number(payload.get("lon"))
    gpsd_host = str(payload.get("gpsd_host") or "")
    gpsd_port = _integer(payload.get("gpsd_port"))
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if mode not in {"static", "gpsd"}:
        failures.append("mode")
    if source != mode:
        failures.append("source")
    if mode == "gpsd":
        if not gpsd_host:
            failures.append("gpsd_host")
        if gpsd_port is None or gpsd_port <= 0:
            failures.append("gpsd_port")
    if lat is None or not -90 <= lat <= 90:
        failures.append("lat")
    if lon is None or not -180 <= lon <= 180:
        failures.append("lon")
    return failures


def _power_report_failures(payload: dict) -> list[str]:
    failures = []
    battery_percent = _integer(payload.get("battery_percent"))
    battery_capacity_wh = _number(payload.get("battery_capacity_wh"))
    available_battery_wh = _number(payload.get("available_battery_wh"))
    critical_reserve_wh = _number(payload.get("critical_reserve_wh"))
    estimated_draw_watts = _number(payload.get("estimated_draw_watts"))
    estimated_runtime_hours = _number(payload.get("estimated_runtime_hours"))
    required_runtime_hours = _number(payload.get("required_runtime_hours"))
    battery_critical_percent = _integer(payload.get("battery_critical_percent"))
    if not _has_text(payload.get("checked_at")):
        failures.append("checked_at")
    if battery_percent is None or battery_percent <= 0:
        failures.append("battery_percent")
    if battery_critical_percent is None:
        failures.append("battery_critical_percent")
    elif battery_percent is not None and battery_percent <= battery_critical_percent:
        failures.append("battery_percent_critical")
    if not isinstance(payload.get("charging"), bool):
        failures.append("charging")
    if not _has_text(payload.get("source")):
        failures.append("source")
    if battery_capacity_wh is None:
        failures.append("battery_capacity")
    expected_reserve_wh = (
        battery_capacity_wh * (battery_critical_percent / 100)
        if battery_capacity_wh is not None
        and battery_critical_percent is not None
        and 0 <= battery_critical_percent <= 100
        else None
    )
    if (
        critical_reserve_wh is None
        or expected_reserve_wh is None
        or abs(critical_reserve_wh - expected_reserve_wh) > 0.1
    ):
        failures.append("critical_reserve")
    expected_available_wh = (
        battery_capacity_wh * (max(0, battery_percent - battery_critical_percent) / 100)
        if battery_capacity_wh is not None
        and battery_percent is not None
        and battery_critical_percent is not None
        and 0 <= battery_percent <= 100
        and 0 <= battery_critical_percent <= 100
        else None
    )
    if (
        available_battery_wh is None
        or expected_available_wh is None
        or abs(available_battery_wh - expected_available_wh) > 0.1
    ):
        failures.append("available_battery")
    expected_runtime = (
        available_battery_wh / estimated_draw_watts
        if available_battery_wh is not None
        and estimated_draw_watts is not None
        and estimated_draw_watts > 0
        else None
    )
    if (
        estimated_runtime_hours is None
        or required_runtime_hours is None
        or estimated_runtime_hours < required_runtime_hours
    ):
        failures.append("runtime")
    if (
        estimated_runtime_hours is None
        or expected_runtime is None
        or abs(estimated_runtime_hours - expected_runtime) > 0.1
    ):
        failures.append("runtime_consistency")
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
    main_pid = _integer(payload.get("main_pid"))
    if main_pid is None or main_pid <= 0:
        failures.append("main_pid")
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
    generated_at = _parse_evidence_timestamp(payload.get("generated_at"))
    timestamp_ok = generated_at is not None
    passed = (
        payload.get("passed") is True
        and timestamp_ok
        and not missing
        and not failed
        and malformed == 0
    )
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
            f"generated_at={'ok' if timestamp_ok else 'missing'}, "
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


def _read_burn_in_samples(
    name: str,
    path: Path,
    raw: bytes,
    *,
    report_path: Path | None = None,
) -> EvidenceItem:
    invalid_lines = 0
    scanned = 0
    camera_failures = 0
    network_failures = 0
    battery_values: list[float] = []
    charging_values: list[bool] = []
    temp_values: list[float] = []
    timestamps: list[datetime] = []
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
        timestamp = _parse_evidence_timestamp(payload.get("ts"))
        if timestamp is None:
            invalid_lines += 1
            continue
        timestamps.append(timestamp.astimezone(timezone.utc))
        if payload.get("camera_ok") is not True:
            camera_failures += 1
        if payload.get("network_online") is not True:
            network_failures += 1
        battery = _number(payload.get("battery_percent"))
        if battery is not None:
            battery_values.append(battery)
        charging = payload.get("battery_charging")
        if isinstance(charging, bool):
            charging_values.append(charging)
        temp = _number(payload.get("temp_c"))
        if temp is not None:
            temp_values.append(temp)

    report = _load_burn_in_sample_report(report_path)
    expected_sample_count = _integer(report.get("sample_count")) if report else None
    expected_camera_failures = _integer(report.get("camera_failures")) if report else None
    expected_network_failures = _integer(report.get("network_failures")) if report else None
    expected_start_battery = _number(report.get("start_battery_percent")) if report else None
    expected_end_battery = _number(report.get("end_battery_percent")) if report else None
    expected_min_battery = _number(report.get("min_battery_percent")) if report else None
    expected_battery_delta = _number(report.get("battery_delta_percent")) if report else None
    expected_charging_seen = report.get("charging_seen") if report else None
    expected_discharging_seen = report.get("discharging_seen") if report else None
    expected_max_temp = _number(report.get("max_temp_c")) if report else None
    expected_max_sample_gap = _number(report.get("max_sample_gap_seconds")) if report else None
    started_at = _parse_evidence_timestamp(report.get("started_at")) if report else None
    ended_at = _parse_evidence_timestamp(report.get("ended_at")) if report else None

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

    report_ok = report is not None
    sample_count_ok = expected_sample_count is not None and scanned == expected_sample_count
    camera_ok = (
        expected_camera_failures is not None and camera_failures == expected_camera_failures == 0
    )
    network_ok = (
        expected_network_failures is not None and network_failures == expected_network_failures == 0
    )
    battery_ok = (
        start_battery is not None
        and start_battery == expected_start_battery
        and end_battery is not None
        and end_battery == expected_end_battery
        and min_battery is not None
        and min_battery == expected_min_battery
        and battery_delta is not None
        and battery_delta == expected_battery_delta
        and isinstance(expected_charging_seen, bool)
        and charging_seen == expected_charging_seen
        and isinstance(expected_discharging_seen, bool)
        and discharging_seen == expected_discharging_seen
    )
    temp_ok = max_temp is not None and max_temp == expected_max_temp

    passed = (
        report_ok
        and invalid_lines == 0
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
            f"report={'ok' if report_ok else 'missing'}, "
            f"scanned={scanned}/{expected_sample_count if expected_sample_count is not None else '-'}, "
            f"camera_failures={camera_failures}/{expected_camera_failures if expected_camera_failures is not None else '-'}, "
            f"network_failures={network_failures}/{expected_network_failures if expected_network_failures is not None else '-'}, "
            f"start_battery={_fmt(start_battery)}/{_fmt(expected_start_battery)}, "
            f"end_battery={_fmt(end_battery)}/{_fmt(expected_end_battery)}, "
            f"min_battery={_fmt(min_battery)}/{_fmt(expected_min_battery)}, "
            f"battery_delta={_fmt_delta(battery_delta)}/{_fmt_delta(expected_battery_delta)}, "
            f"charging_seen={charging_seen}/{expected_charging_seen if expected_charging_seen is not None else '-'}, "
            f"discharging_seen={discharging_seen}/{expected_discharging_seen if expected_discharging_seen is not None else '-'}, "
            f"max_temp={_fmt(max_temp)}/{_fmt(expected_max_temp)}, "
            f"max_sample_gap={_fmt_seconds(max_observed_gap)}/{_fmt_seconds(expected_max_sample_gap)}, "
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


def _load_burn_in_sample_report(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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


def _read_autopay_provider_alignment(
    autopay_path: Path,
    endpoints_path: Path,
) -> EvidenceItem:
    path = f"{autopay_path} + {endpoints_path}"
    if not autopay_path.exists() or not endpoints_path.exists():
        missing = [
            str(missing_path)
            for missing_path in (autopay_path, endpoints_path)
            if not missing_path.exists()
        ]
        return EvidenceItem(
            "autopay_provider_alignment",
            path,
            False,
            False,
            None,
            None,
            None,
            _format("autopay_provider_alignment"),
            f"missing {', '.join(missing)}",
        )

    try:
        autopay = json.loads(autopay_path.read_text())
        endpoints = json.loads(endpoints_path.read_text())
    except json.JSONDecodeError as exc:
        return EvidenceItem(
            "autopay_provider_alignment",
            path,
            True,
            False,
            None,
            None,
            None,
            _format("autopay_provider_alignment"),
            f"invalid json {exc}",
        )
    if not isinstance(autopay, dict) or not isinstance(endpoints, dict):
        return EvidenceItem(
            "autopay_provider_alignment",
            path,
            True,
            True,
            False,
            None,
            None,
            _format("autopay_provider_alignment"),
            "json is not an object",
        )

    provider = str(autopay.get("provider") or "").strip().lower()
    hints = endpoints.get("config_hints") if isinstance(endpoints.get("config_hints"), dict) else {}
    flow = endpoints.get("flow_summary") if isinstance(endpoints.get("flow_summary"), dict) else {}
    paybyphone_hints_ok = all(
        bool(hints.get(key))
        for key in ("base_url", "auth_url", "client_id", "rate_option_id", "payment_method_id")
    )
    paybyphone_flow_ok = all(
        bool(flow.get(key))
        for key in (
            "auth",
            "location_lookup",
            "session_start",
            "active_session_check",
            "session_stop",
        )
    )
    passed = provider == "paybyphone" and paybyphone_hints_ok and paybyphone_flow_ok
    raw = autopay_path.read_bytes() + endpoints_path.read_bytes()
    return EvidenceItem(
        "autopay_provider_alignment",
        path,
        True,
        True,
        passed,
        len(raw),
        hashlib.sha256(raw).hexdigest(),
        _format("autopay_provider_alignment"),
        (
            f"provider={provider or '-'}/paybyphone, "
            f"hints={'ok' if paybyphone_hints_ok else 'missing'}, "
            f"flow={'ok' if paybyphone_flow_ok else 'missing'}"
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
    duration_minutes = payload.get("duration_minutes") if isinstance(payload, dict) else None
    active_duration = (
        payload.get("active_session_duration_minutes") if isinstance(payload, dict) else None
    )
    duration_verified = (
        payload.get("duration_verified") is True if isinstance(payload, dict) else False
    )
    duration_ok = (
        isinstance(duration_minutes, int)
        and isinstance(active_duration, int)
        and duration_minutes == active_duration
    )
    provider = payload.get("provider") if isinstance(payload, dict) else None
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    zone_id = payload.get("zone_id") if isinstance(payload, dict) else None
    session_location_id = payload.get("session_location_id") if isinstance(payload, dict) else None
    session_zone_ok = bool(zone_id) and session_location_id == zone_id
    complete = (
        passed
        and not dry_run
        and amount_ok
        and active_verified
        and stopped
        and stop_verified
        and duration_verified
        and duration_ok
        and bool(provider)
        and bool(session_id)
        and bool(zone_id)
        and session_zone_ok
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
            f"duration={duration_minutes}/{active_duration}, duration_verified={duration_verified}, "
            f"provider={'ok' if provider else 'missing'}, "
            f"session={'ok' if session_id else 'missing'}, zone={'ok' if zone_id else 'missing'}, "
            f"session_zone={session_location_id or '-'}/{zone_id or '-'}"
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
    webhook_hash = str(payload.get("webhook_hash") or "") if isinstance(payload, dict) else ""
    title = str(payload.get("title") or "") if isinstance(payload, dict) else ""
    message = str(payload.get("message") or "") if isinstance(payload, dict) else ""
    sound = payload.get("sound") is True if isinstance(payload, dict) else False
    tested_at = (
        _parse_evidence_timestamp(payload.get("tested_at")) if isinstance(payload, dict) else None
    )
    status_ok = isinstance(status_code, int) and 200 <= status_code < 300
    battery_message_ok = _is_battery_notification_text(f"{title} {message}")
    complete = (
        passed
        and status_ok
        and bool(webhook_host)
        and bool(webhook_hash)
        and bool(title)
        and bool(message)
        and sound
        and tested_at is not None
        and battery_message_ok
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
            f"passed={passed}, status={status_code}, "
            f"host={'ok' if webhook_host else 'missing'}, "
            f"hash={'ok' if webhook_hash else 'missing'}, "
            f"title={'ok' if title else 'missing'}, "
            f"message={'ok' if message else 'missing'}, "
            f"sound={sound}, "
            f"tested_at={'ok' if tested_at is not None else 'missing'}, "
            f"battery_message={battery_message_ok}"
        ),
    )


def _is_battery_notification_text(value: str) -> bool:
    normalized = value.lower()
    has_battery = any(token in normalized for token in ("batterie", "battery"))
    has_low = any(token in normalized for token in ("faible", "low", "manquer"))
    return has_battery and has_low


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
    true_positives = _integer(payload.get("true_positives")) if isinstance(payload, dict) else None
    false_positives = (
        _integer(payload.get("false_positives")) if isinstance(payload, dict) else None
    )
    false_negatives = (
        _integer(payload.get("false_negatives")) if isinstance(payload, dict) else None
    )
    invalid_images = _integer(payload.get("invalid_images")) if isinstance(payload, dict) else None
    invalid_labels = _integer(payload.get("invalid_labels")) if isinstance(payload, dict) else None
    model_path = str(payload.get("model_path") or "") if isinstance(payload, dict) else ""
    dataset_path = str(payload.get("dataset_path") or "") if isinstance(payload, dict) else ""
    required_class = str(payload.get("required_class") or "") if isinstance(payload, dict) else ""
    precision = _number(payload.get("precision")) if isinstance(payload, dict) else None
    expected_recall = _metric_ratio(true_positives, true_positives, false_negatives)
    expected_precision = _metric_ratio(true_positives, true_positives, false_positives)
    expected_fp_per_hour = (
        false_positives / evaluated_hours
        if false_positives is not None and evaluated_hours is not None and evaluated_hours > 0
        else None
    )
    metrics_consistent = (
        recall is not None
        and expected_recall is not None
        and abs(recall - expected_recall) <= 0.001
        and precision is not None
        and expected_precision is not None
        and abs(precision - expected_precision) <= 0.001
        and false_positive_per_hour is not None
        and expected_fp_per_hour is not None
        and abs(false_positive_per_hour - expected_fp_per_hour) <= 0.001
    )
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
        and true_positives is not None
        and true_positives > 0
        and false_positives is not None
        and false_negatives is not None
        and invalid_images == 0
        and invalid_labels == 0
        and metrics_consistent
        and required_class == "control_vehicle"
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
            f"true_positives={true_positives}, false_positives={false_positives}, "
            f"false_negatives={false_negatives}, invalid_images={invalid_images}, "
            f"invalid_labels={invalid_labels}, "
            f"metrics_consistent={metrics_consistent}, "
            f"class={required_class or '-'}/control_vehicle, "
            f"model={'ok' if model_path else 'missing'}, "
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
    detections_seen = (
        _integer(payload.get("detections_seen")) if isinstance(payload, dict) else None
    )
    measured_fps = _number(payload.get("measured_fps")) if isinstance(payload, dict) else None
    min_fps = _number(payload.get("min_fps")) if isinstance(payload, dict) else None
    model_path = str(payload.get("model_path") or "") if isinstance(payload, dict) else ""
    device = str(payload.get("device") or "") if isinstance(payload, dict) else ""
    target_labels = payload.get("target_labels") if isinstance(payload, dict) else None
    target_ok = isinstance(target_labels, list) and "control_vehicle" in target_labels
    ok = (
        passed
        and frames_processed is not None
        and frames_processed > 0
        and detections_seen is not None
        and detections_seen > 0
        and measured_fps is not None
        and min_fps is not None
        and measured_fps >= min_fps
        and target_ok
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
            f"frames={frames_processed}, detections={detections_seen}, "
            f"target={','.join(str(label) for label in target_labels) if isinstance(target_labels, list) else '-'}/control_vehicle, "
            f"model={'ok' if model_path else 'missing'}, "
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
    if name == "runtime_alignment":
        return "derived"
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


def _parse_evidence_timestamp(value: object) -> datetime | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fmt_seconds(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}s"


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(
        strict=False,
    )


def _path_exists(value: str) -> bool:
    return Path(value).expanduser().exists()


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}"


def _metric_ratio(
    numerator: int | None,
    denominator_left: int | None,
    denominator_right: int | None,
) -> float | None:
    if numerator is None or denominator_left is None or denominator_right is None:
        return None
    denominator = denominator_left + denominator_right
    if denominator <= 0:
        return None
    return numerator / denominator
