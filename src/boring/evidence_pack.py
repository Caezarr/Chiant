"""Pack de preuves terrain pour une Boring Box."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from boring.runtime_events import BLOCKING_RUNTIME_EVENTS


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
        "burn_in_samples",
        "notification_test",
        "paybyphone_endpoints",
        "runtime_events",
    }:
        return item.passed is True
    if item.name == "hardware_profile":
        return item.passed is not False
    return item.passed is True


def _read_item(name: str, path: Path) -> EvidenceItem:
    if not path.exists():
        return EvidenceItem(
            name, str(path), False, False, None, None, None, _format(name), "missing"
        )
    raw = path.read_bytes()
    if name == "autopay_smoke":
        return _read_autopay_smoke(name, path, raw)
    if name == "burn_in_samples":
        return _read_burn_in_samples(name, path, raw)
    if name == "notification_test":
        return _read_notification_test(name, path, raw)
    if name == "paybyphone_endpoints":
        return _read_paybyphone_endpoints(name, path, raw)
    if name == "runtime_events":
        return _read_runtime_events(name, path, raw)
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
