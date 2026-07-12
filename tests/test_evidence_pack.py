from __future__ import annotations

import json
from pathlib import Path

from boring.evidence_pack import build_evidence_pack, default_evidence_paths, write_pack


def test_evidence_pack_passes_when_all_reports_are_present(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    assert pack.passed is True
    assert all(item.present for item in pack.items)
    assert all(item.valid_json for item in pack.items)


def test_evidence_pack_fails_when_report_is_missing(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["burn_in"].unlink()

    pack = build_evidence_pack(paths)

    assert pack.passed is False
    missing = [item for item in pack.items if item.name == "burn_in"][0]
    assert missing.present is False
    assert missing.detail == "missing"


def test_evidence_pack_fails_when_report_failed(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["autopay_smoke"].write_text(json.dumps({"passed": False}))

    pack = build_evidence_pack(paths)

    assert pack.passed is False
    autopay = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert autopay.passed is False


def test_evidence_pack_fails_when_required_report_has_no_passed_flag(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["vision_eval"].write_text(json.dumps({"metrics": {"recall": 0.95}}))

    pack = build_evidence_pack(paths)

    assert pack.passed is False
    vision_eval = [item for item in pack.items if item.name == "vision_eval"][0]
    assert vision_eval.passed is None


def test_write_pack_includes_passed(tmp_path: Path):
    pack = build_evidence_pack(_write_evidence(tmp_path))
    output = tmp_path / "reports" / "evidence-pack.json"

    write_pack(pack, output)

    payload = json.loads(output.read_text())
    assert payload["passed"] is True
    assert payload["items"]


def test_evidence_pack_includes_file_digest_and_size(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    autopay = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert autopay.size_bytes == paths["autopay_smoke"].stat().st_size
    assert autopay.sha256
    assert len(autopay.sha256) == 64


def test_evidence_pack_omits_digest_for_missing_report(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["burn_in"].unlink()

    pack = build_evidence_pack(paths)

    missing = [item for item in pack.items if item.name == "burn_in"][0]
    assert missing.size_bytes is None
    assert missing.sha256 is None


def test_evidence_pack_digest_changes_when_report_changes(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    first = build_evidence_pack(paths)
    first_autopay = [item for item in first.items if item.name == "autopay_smoke"][0]

    paths["autopay_smoke"].write_text(json.dumps({"passed": True, "session_id": "new"}))
    second = build_evidence_pack(paths)
    second_autopay = [item for item in second.items if item.name == "autopay_smoke"][0]

    assert first_autopay.sha256 != second_autopay.sha256


def test_evidence_pack_requires_complete_autopay_smoke(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert item.passed is True
    assert "dry_run=False" in item.detail
    assert "stop_verified=True" in item.detail
    assert "session=ok" in item.detail


def test_evidence_pack_rejects_autopay_smoke_dry_run(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["autopay_smoke"].read_text())
    payload["dry_run"] = True
    paths["autopay_smoke"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "dry_run=True" in item.detail


def test_evidence_pack_rejects_autopay_smoke_without_verified_stop(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["autopay_smoke"].read_text())
    payload["stop_verified"] = False
    paths["autopay_smoke"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "stop_verified=False" in item.detail


def test_evidence_pack_rejects_autopay_smoke_without_session_id(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["autopay_smoke"].read_text())
    payload["session_id"] = None
    paths["autopay_smoke"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "session=missing" in item.detail


def test_evidence_pack_requires_complete_notification_test(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "notification_test"][0]
    assert item.passed is True
    assert "status=204" in item.detail
    assert "host=ok" in item.detail


def test_evidence_pack_rejects_notification_test_non_2xx(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["notification_test"].read_text())
    payload["passed"] = False
    payload["status_code"] = 500
    payload["error"] = "HTTP 500"
    paths["notification_test"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "notification_test"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "status=500" in item.detail


def test_evidence_pack_rejects_notification_test_without_host(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["notification_test"].read_text())
    payload["webhook_host"] = ""
    paths["notification_test"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "notification_test"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "host=missing" in item.detail


def test_evidence_pack_includes_runtime_events_jsonl(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "runtime_events"][0]
    assert item.format == "jsonl"
    assert item.passed is True
    assert "heartbeat=True" in item.detail


def test_evidence_pack_rejects_runtime_events_without_heartbeat(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "startup"}) + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "runtime_events"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "heartbeat=False" in item.detail


def test_evidence_pack_rejects_blocking_runtime_event(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "heartbeat"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T00:05:00+00:00", "event": "network_offline"})
        + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "runtime_events"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "network_offline@line2" in item.detail


def test_evidence_pack_includes_burn_in_samples_jsonl(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert item.format == "jsonl"
    assert item.passed is True
    assert "battery_samples=1" in item.detail
    assert "temp_samples=1" in item.detail


def test_evidence_pack_rejects_burn_in_sample_camera_failure(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["burn_in_samples"].write_text(
        json.dumps(
            {
                "ts": 1.0,
                "camera_ok": False,
                "network_online": True,
                "battery_percent": 82,
                "temp_c": 44.0,
            }
        )
        + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "camera_failures=1" in item.detail


def test_evidence_pack_rejects_burn_in_samples_without_power_metrics(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["burn_in_samples"].write_text(
        json.dumps(
            {
                "ts": 1.0,
                "camera_ok": True,
                "network_online": True,
                "battery_percent": None,
                "temp_c": None,
            }
        )
        + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "battery_samples=0" in item.detail
    assert "temp_samples=0" in item.detail


def test_evidence_pack_includes_paybyphone_endpoints(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "paybyphone_endpoints"][0]
    assert item.format == "json"
    assert item.passed is True
    assert "missing_hints=-" in item.detail
    assert "missing_flow=-" in item.detail


def test_evidence_pack_rejects_paybyphone_endpoints_without_stop_flow(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["paybyphone_endpoints"].read_text())
    payload["flow_summary"]["session_stop"] = False
    paths["paybyphone_endpoints"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "paybyphone_endpoints"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "missing_flow=session_stop" in item.detail


def test_evidence_pack_rejects_paybyphone_endpoints_without_payment_method(
    tmp_path: Path,
):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["paybyphone_endpoints"].read_text())
    payload["config_hints"]["payment_method_id"] = ""
    paths["paybyphone_endpoints"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "paybyphone_endpoints"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "missing_hints=payment_method_id" in item.detail


def test_default_evidence_paths_include_box_ready():
    paths = default_evidence_paths()

    assert paths["box_ready"] == Path("reports/box-readiness.json")
    assert paths["autopay_smoke"] == Path("reports/autopay-smoke.json")
    assert paths["systemd_runtime"] == Path("reports/systemd-check.json")
    assert paths["position_runtime"] == Path("reports/position-check.json")
    assert paths["camera_runtime"] == Path("reports/camera-check.json")
    assert paths["network_runtime"] == Path("reports/network-check.json")
    assert paths["power_runtime"] == Path("reports/power-check.json")
    assert paths["runtime_events"] == Path("/var/lib/boring/events.jsonl")
    assert paths["paybyphone_endpoints"] == Path("scripts/paybyphone_endpoints.json")
    assert paths["burn_in_samples"] == Path("burn-in/samples.jsonl")


def _write_evidence(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "box_ready": tmp_path / "reports" / "box-readiness.json",
        "hardware_profile": tmp_path / "deploy" / "pi" / "hardware-profile.json",
        "systemd_runtime": tmp_path / "reports" / "systemd-check.json",
        "position_runtime": tmp_path / "reports" / "position-check.json",
        "camera_runtime": tmp_path / "reports" / "camera-check.json",
        "network_runtime": tmp_path / "reports" / "network-check.json",
        "power_runtime": tmp_path / "reports" / "power-check.json",
        "runtime_events": tmp_path / "events.jsonl",
        "vision_eval": tmp_path / "reports" / "vision-eval.json",
        "vision_benchmark": tmp_path / "reports" / "vision-benchmark.json",
        "paybyphone_endpoints": tmp_path / "scripts" / "paybyphone_endpoints.json",
        "autopay_smoke": tmp_path / "reports" / "autopay-smoke.json",
        "notification_test": tmp_path / "reports" / "notification-test.json",
        "burn_in": tmp_path / "burn-in" / "report.json",
        "burn_in_samples": tmp_path / "burn-in" / "samples.jsonl",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"passed": True}))
    paths["autopay_smoke"].write_text(
        json.dumps(
            {
                "passed": True,
                "provider": "paybyphone",
                "dry_run": False,
                "plate": "AB-123-CD",
                "zone_id": "zone-1",
                "session_id": "session-1",
                "amount_cents": 120,
                "duration_minutes": 15,
                "lat": 50.6371,
                "lon": 3.0633,
                "active_session_verified": True,
                "stopped": True,
                "stop_verified": True,
                "tested_at": "2026-01-01T00:00:00+00:00",
                "error": None,
            }
        )
    )
    paths["notification_test"].write_text(
        json.dumps(
            {
                "passed": True,
                "webhook_host": "notify.example.test",
                "status_code": 204,
                "title": "Boring Box - test notification",
                "message": "Canal notification pret pour batterie faible.",
                "tested_at": "2026-01-01T00:00:00+00:00",
                "error": None,
            }
        )
    )
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "heartbeat"}) + "\n"
    )
    paths["burn_in_samples"].write_text(
        json.dumps(
            {
                "ts": 1.0,
                "camera_ok": True,
                "network_online": True,
                "battery_percent": 82,
                "temp_c": 44.0,
            }
        )
        + "\n"
    )
    paths["paybyphone_endpoints"].write_text(
        json.dumps(
            {
                "config_hints": {
                    "base_url": "https://api.example.test",
                    "auth_url": "https://api.example.test/auth",
                    "client_id": "client",
                    "rate_option_id": "rate",
                    "payment_method_id": "pm",
                },
                "flow_summary": {
                    "auth": True,
                    "account_lookup": True,
                    "location_lookup": True,
                    "session_start": True,
                    "active_session_check": True,
                    "session_stop": True,
                    "successful_statuses": 6,
                    "failed_statuses": 0,
                },
            }
        )
    )
    paths["hardware_profile"].write_text(json.dumps({"board": {"model": "raspberry-pi-5"}}))
    return paths
