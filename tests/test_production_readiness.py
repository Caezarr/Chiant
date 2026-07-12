from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boring.production_readiness import audit_production_readiness, write_report
from boring.storage import DiskStatus


def test_production_readiness_passes_with_all_artifacts(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        min_burn_in_hours=10,
    )

    assert report.passed is True
    assert all(check.ok for check in report.checks)


def test_production_readiness_fails_when_burn_in_too_short(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, burn_in_hours=2)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        min_burn_in_hours=10,
    )

    assert report.passed is False
    assert any(check.name == "burn_in" and not check.ok for check in report.checks)


def test_production_readiness_can_run_rehearsal_without_edge_or_real_payment(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, include_edge=False)
    env = _ready_env()
    env["PAYMENT_DRY_RUN"] = "true"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        require_edge_export=False,
        require_real_payment=False,
    )

    assert report.passed is True


def test_production_readiness_fails_without_charge_validation(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, charging_seen=False)

    strict = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )
    rehearsal = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        require_charging_seen=False,
    )

    assert strict.passed is False
    assert any(check.name == "burn_in" and not check.ok for check in strict.checks)
    assert rehearsal.passed is True


def test_production_readiness_fails_when_disk_space_is_low(tmp_path: Path, monkeypatch):
    artifacts = _write_ready_artifacts(tmp_path)

    class FakeDisk:
        def __init__(self, path: Path) -> None:
            self.path = path

        def check(self) -> DiskStatus:
            return DiskStatus(str(self.path), free_mb=100, total_mb=10_000)

    monkeypatch.setattr("boring.production_readiness.DiskSpaceMonitor", FakeDisk)
    env = _ready_env()
    env["BOX_DISK_MIN_FREE_MB"] = "512"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "disk_space" and not check.ok for check in report.checks)


def test_production_readiness_fails_without_hardware_profile(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=tmp_path / "missing-hardware.json",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "hardware" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_vehicle_charge_cannot_recover(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["VEHICLE_CHARGE_WATTS"] = "6"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "power_budget" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_hardware_and_env_power_disagree(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, hardware_battery_wh=80)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "hardware_env_consistency" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_vision_eval_fails(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, vision_eval_passed=False, vision_recall=0.60)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "vision_eval" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_vision_eval_has_no_frames(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload["frames_evaluated"] = 0
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "vision_eval" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_benchmark_fails(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, benchmark_passed=False, benchmark_fps=0.5)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "vision_benchmark" and not check.ok for check in report.checks)


def test_production_readiness_requires_benchmark_threshold_from_hardware_preset(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, benchmark_fps=2.5, benchmark_min_fps=1.0)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    benchmark = [check for check in report.checks if check.name == "vision_benchmark"][0]
    assert "required=2.00" in benchmark.detail


def test_production_readiness_fails_without_notification_webhook(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["BORING_NOTIFY_WEBHOOK_URL"] = ""

    strict = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )
    rehearsal = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        require_notification_webhook=False,
    )

    assert strict.passed is False
    assert any(check.name == "notification_webhook" and not check.ok for check in strict.checks)
    assert rehearsal.passed is True


def test_production_readiness_fails_without_network_recovery(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["NETWORK_RECOVERY_COMMAND"] = ""

    strict = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )
    rehearsal = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        require_network_recovery=False,
    )

    assert strict.passed is False
    assert any(check.name == "network_recovery" and not check.ok for check in strict.checks)
    assert rehearsal.passed is True


def test_production_readiness_fails_when_notification_test_fails(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, notification_passed=False)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "notification_test" and not check.ok for check in report.checks)


def test_production_readiness_requires_notification_test_for_configured_webhook(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["notification"].read_text())
    payload["webhook_host"] = "old-notify.example.test"
    artifacts["notification"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "notification_test"][0]
    assert "expected_host=notify.example.test" in check.detail


def test_production_readiness_fails_when_autopay_smoke_fails(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, autopay_smoke_passed=False)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "autopay_smoke" and not check.ok for check in report.checks)


def test_production_readiness_requires_autopay_stop_verification(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["stop_verified"] = False
    artifacts["autopay_smoke"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "autopay_smoke" and not check.ok for check in report.checks)


def test_production_readiness_rejects_autopay_smoke_for_other_plate(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["plate"] = "ZZ-999-ZZ"
    artifacts["autopay_smoke"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "autopay_smoke"][0]
    assert check.ok is False
    assert "plate=ZZ-999-ZZ/AB-123-CD" in check.detail


def test_production_readiness_rejects_autopay_smoke_for_other_provider(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["provider"] = "easypark"
    artifacts["autopay_smoke"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "autopay_smoke"][0]
    assert check.ok is False
    assert "provider=easypark/paybyphone" in check.detail


def test_production_readiness_rejects_autopay_smoke_for_other_forced_zone(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["PAYBYPHONE_LOCATION_ID"] = "zone-expected"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "autopay_smoke"][0]
    assert check.ok is False
    assert "zone=zone-1/zone-expected" in check.detail


def test_production_readiness_rejects_stale_reports(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now - timedelta(hours=96))

    report = audit_production_readiness(
        env=_ready_env(),
        now=now,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "report_freshness"][0]
    assert check.ok is False
    assert "96.0h>72.0h" in check.detail


def test_production_readiness_rejects_report_without_timestamp(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload.pop("generated_at")
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "report_freshness"][0]
    assert check.ok is False
    assert "vision_eval=missing_timestamp" in check.detail


def test_production_readiness_can_disable_report_freshness_for_rehearsal(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now - timedelta(hours=720))
    env = _ready_env()
    env["BOX_READINESS_MAX_REPORT_AGE_HOURS"] = "0"

    report = audit_production_readiness(
        env=env,
        now=now,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is True
    check = [check for check in report.checks if check.name == "report_freshness"][0]
    assert check.detail == "disabled"


def test_production_readiness_allows_missing_runtime_event_log(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path / "events.jsonl",
    )

    assert report.passed is True
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is True
    assert "missing optional" in check.detail


def test_production_readiness_ignores_runtime_events_before_burn_in(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "ts": (now - timedelta(hours=11)).isoformat(),
                "event": "notification_failed",
            }
        )
        + "\n"
    )

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=events,
    )

    assert report.passed is True
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is True
    assert "scanned=0" in check.detail


def test_production_readiness_rejects_blocking_runtime_event(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "ts": (now - timedelta(hours=1)).isoformat(),
                "event": "payment_skipped_battery_critical",
                "plate": "AB-123-CD",
            }
        )
        + "\n"
    )

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=events,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "payment_skipped_battery_critical@line1" in check.detail


def test_write_report_includes_passed(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )
    output = tmp_path / "reports" / "box.json"

    write_report(report, output)

    payload = json.loads(output.read_text())
    assert payload["passed"] is True


def _ready_env() -> dict[str, str]:
    return {
        "PAYMENT_MODE": "auto",
        "PAYMENT_PROVIDER": "paybyphone",
        "PAYMENT_DRY_RUN": "false",
        "DEFAULT_VEHICLE_PLATE": "AB-123-CD",
        "DEFAULT_DURATION_MINUTES": "15",
        "COOLDOWN_MINUTES": "15",
        "PAYBYPHONE_USERNAME": "user",
        "PAYBYPHONE_PASSWORD": "secret",
        "PAYBYPHONE_API_BASE": "https://api.example.test",
        "PAYBYPHONE_AUTH_URL": "https://api.example.test/auth",
        "PAYBYPHONE_CLIENT_ID": "client",
        "PAYBYPHONE_RATE_OPTION_ID": "rate",
        "PAYBYPHONE_PAYMENT_METHOD_ID": "pm",
        "BOX_REQUIRE_GEOFENCE": "true",
        "POSITION_MODE": "static",
        "BOX_LAT": "50.6371",
        "BOX_LON": "3.0633",
        "BATTERY_CAPACITY_WH": "100",
        "ESTIMATED_DRAW_WATTS": "8",
        "REQUIRED_RUNTIME_HOURS": "10",
        "POWER_RESERVE_PERCENT": "15",
        "VEHICLE_CHARGE_WATTS": "30",
        "DAILY_DRIVE_RECHARGE_HOURS": "1",
        "CHARGE_EFFICIENCY": "0.85",
        "NETWORK_RECOVERY_COMMAND": "systemctl restart NetworkManager",
        "NETWORK_RECOVERY_COOLDOWN_SECONDS": "300",
        "NETWORK_RECOVERY_TIMEOUT_SECONDS": "20",
        "BORING_NOTIFY_WEBHOOK_URL": "https://notify.example.test/boring",
    }


def _write_ready_artifacts(
    tmp_path: Path,
    *,
    report_time: datetime | None = None,
    burn_in_hours: float = 10,
    include_edge: bool = True,
    charging_seen: bool = True,
    benchmark_passed: bool = True,
    benchmark_fps: float = 2.0,
    benchmark_min_fps: float = 2.0,
    notification_passed: bool = True,
    autopay_smoke_passed: bool = True,
    hardware_battery_wh: float = 100,
    hardware_charge_watts: float = 30,
    vision_eval_passed: bool = True,
    vision_recall: float = 0.93,
    vision_false_positive_per_hour: float = 0.5,
) -> dict[str, Path]:
    report_time = report_time or datetime.now(timezone.utc)
    report_time_iso = report_time.isoformat()
    manifest = tmp_path / "datasets" / "baseline" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    lines = []
    for index in range(100):
        lines.append(
            json.dumps(
                {
                    "profile": "positives",
                    "path": f"p{index}.jpg",
                    "license_reviewed": True,
                    "license_status": "cc-by",
                }
            )
        )
    for index in range(500):
        lines.append(
            json.dumps(
                {
                    "profile": "negatives",
                    "path": f"n{index}.jpg",
                    "license_reviewed": True,
                    "license_status": "open-images",
                }
            )
        )
    manifest.write_text("\n".join(lines) + "\n")

    dataset = tmp_path / "datasets" / "control_vehicle_v1"
    train_dir = dataset / "train" / "images"
    valid_dir = dataset / "valid" / "images"
    train_dir.mkdir(parents=True)
    valid_dir.mkdir(parents=True)
    (dataset / "data.yaml").write_text("names: ['control_vehicle']\n")
    for index in range(300):
        (train_dir / f"train-{index}.jpg").write_bytes(b"image")
    for index in range(50):
        (valid_dir / f"valid-{index}.jpg").write_bytes(b"image")

    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")
    if include_edge:
        (model.parent / "best.onnx").write_bytes(b"edge")

    endpoints = tmp_path / "scripts" / "paybyphone_endpoints.json"
    endpoints.parent.mkdir()
    endpoints.write_text(
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

    hardware = tmp_path / "deploy" / "pi" / "hardware-profile.json"
    hardware.parent.mkdir(parents=True)
    hardware.write_text(
        json.dumps(
            {
                "preset_id": "pi5-production",
                "board": {"model": "raspberry-pi-5", "ram_gb": 8},
                "camera": {"type": "usb-uvc", "device": "/dev/video0"},
                "storage": {"capacity_gb": 64, "endurance": True},
                "power": {
                    "ups_power_supply": True,
                    "battery_capacity_wh": hardware_battery_wh,
                    "vehicle_charge_watts": hardware_charge_watts,
                },
                "network": {"mode": "hotspot"},
                "runtime": {"detection_fps": 2.0, "min_benchmark_fps": 2.0},
            }
        )
    )

    vision_eval = tmp_path / "reports" / "vision-eval.json"
    vision_eval.parent.mkdir()
    vision_eval.write_text(
        json.dumps(
            {
                "model_path": str(model),
                "dataset_id": "field-pi5-daylight-v1",
                "recall": vision_recall,
                "precision": 0.98,
                "false_positive_per_hour": vision_false_positive_per_hour,
                "evaluated_hours": 3.0,
                "frames_evaluated": 10_800,
                "true_positives": 93,
                "false_positives": 1,
                "false_negatives": 7,
                "invalid_images": 0,
                "generated_at": report_time_iso,
                "min_recall": 0.90,
                "max_false_positive_per_hour": 1.0,
                "passed": vision_eval_passed,
            }
        )
    )

    burn_in = tmp_path / "burn-in" / "report.json"
    burn_in.parent.mkdir()
    burn_in.write_text(
        json.dumps(
            {
                "passed": True,
                "started_at": report_time.timestamp() - burn_in_hours * 3600,
                "ended_at": report_time.timestamp(),
                "duration_seconds": burn_in_hours * 3600,
                "camera_failures": 0,
                "network_failures": 0,
                "battery_critical_seen": False,
                "thermal_critical_seen": False,
                "charging_seen": charging_seen,
                "discharging_seen": True,
                "start_battery_percent": 70,
                "end_battery_percent": 82 if charging_seen else 62,
                "battery_delta_percent": 12 if charging_seen else -8,
            }
        )
    )

    benchmark = tmp_path / "reports" / "vision-benchmark.json"
    benchmark.parent.mkdir(exist_ok=True)
    benchmark.write_text(
        json.dumps(
            {
                "model_path": str(model),
                "device": "cpu",
                "frames_processed": 120,
                "detections_seen": 0,
                "duration_seconds": 60.0,
                "measured_fps": benchmark_fps,
                "min_fps": benchmark_min_fps,
                "passed": benchmark_passed,
                "generated_at": report_time_iso,
            }
        )
    )

    autopay_smoke = tmp_path / "reports" / "autopay-smoke.json"
    autopay_smoke.write_text(
        json.dumps(
            {
                "passed": autopay_smoke_passed,
                "provider": "paybyphone",
                "dry_run": False,
                "plate": "AB-123-CD",
                "zone_id": "zone-1",
                "session_id": "session-1",
                "amount_cents": 120 if autopay_smoke_passed else 0,
                "active_session_verified": autopay_smoke_passed,
                "stopped": autopay_smoke_passed,
                "stop_verified": autopay_smoke_passed,
                "tested_at": report_time_iso,
                "error": None if autopay_smoke_passed else "smoke failed",
            }
        )
    )

    notification = tmp_path / "reports" / "notification-test.json"
    notification.write_text(
        json.dumps(
            {
                "passed": notification_passed,
                "webhook_host": "notify.example.test",
                "status_code": 204 if notification_passed else 500,
                "title": "Boring Box - test notification",
                "message": "Canal notification pret pour batterie faible.",
                "tested_at": report_time_iso,
                "error": None if notification_passed else "HTTP 500",
            }
        )
    )

    return {
        "manifest": manifest,
        "dataset": dataset,
        "model": model,
        "endpoints": endpoints,
        "hardware": hardware,
        "vision_eval": vision_eval,
        "benchmark": benchmark,
        "autopay_smoke": autopay_smoke,
        "notification": notification,
        "burn_in": burn_in,
    }
