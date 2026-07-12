from __future__ import annotations

import hashlib
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_report_records_generation_time(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)

    report = audit_production_readiness(
        env=_ready_env(),
        now=now,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.generated_at == "2026-07-12T08:00:00+00:00"
    assert report.to_dict()["generated_at"] == report.generated_at


def test_production_readiness_fails_when_burn_in_too_short(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, burn_in_hours=2)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_fails_without_discharge_validation(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, discharging_seen=False)

    strict = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
        require_charging_seen=False,
    )

    assert strict.passed is False
    check = [check for check in strict.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "discharging_seen=False" in check.detail
    assert rehearsal.passed is True


def test_production_readiness_fails_without_burn_in_battery_metrics(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["burn_in"].read_text())
    payload["sample_count"] = 0
    payload["start_battery_percent"] = None
    payload["end_battery_percent"] = None
    payload["min_battery_percent"] = None
    payload["battery_delta_percent"] = None
    artifacts["burn_in"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "samples=0" in check.detail
    assert "battery=-" in check.detail


def test_production_readiness_fails_without_burn_in_thermal_metrics(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["burn_in"].read_text())
    payload["max_temp_c"] = None
    artifacts["burn_in"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "max_temp=-" in check.detail


def test_production_readiness_fails_without_burn_in_samples(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    artifacts["burn_in_samples"].unlink()

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in_samples"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_fails_when_burn_in_samples_do_not_match_report(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    artifacts["burn_in_samples"].write_text(
        json.dumps(
            {
                "ts": 1.0,
                "camera_ok": True,
                "network_online": True,
                "battery_percent": 70,
                "temp_c": 55.0,
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in_samples"][0]
    assert check.ok is False
    assert "scanned=1/600" in check.detail


def test_production_readiness_recomputes_burn_in_charge_cycle_from_samples(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    sample_lines = []
    for raw_line in artifacts["burn_in_samples"].read_text().splitlines():
        payload = json.loads(raw_line)
        payload["battery_charging"] = False
        sample_lines.append(json.dumps(payload))
    artifacts["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in_samples"][0]
    assert check.ok is False
    assert "charging_seen=False/True" in check.detail


def test_production_readiness_rejects_burn_in_samples_outside_report_window(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    sample_lines = []
    for raw_line in artifacts["burn_in_samples"].read_text().splitlines():
        payload = json.loads(raw_line)
        payload["ts"] = payload["ts"] - 3600
        sample_lines.append(json.dumps(payload))
    artifacts["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in_samples"][0]
    assert check.ok is False
    assert "timestamps_in_window=False" in check.detail


def test_production_readiness_rejects_non_monotonic_burn_in_samples(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    sample_lines = []
    report_payload = json.loads(artifacts["burn_in"].read_text())
    for line_number, raw_line in enumerate(artifacts["burn_in_samples"].read_text().splitlines()):
        payload = json.loads(raw_line)
        if line_number == 1:
            payload["ts"] = report_payload["ended_at"]
        sample_lines.append(json.dumps(payload))
    artifacts["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in_samples"][0]
    assert check.ok is False
    assert "timestamps_monotonic=False" in check.detail


def test_production_readiness_recomputes_burn_in_thermal_threshold(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["burn_in"].read_text())
    payload["max_temp_c"] = 86
    payload["thermal_critical_seen"] = False
    payload["passed"] = True
    artifacts["burn_in"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "max_temp=86.0C/85.0C" in check.detail


def test_production_readiness_rejects_low_battery_burn_in(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["burn_in"].read_text())
    payload["battery_low_seen"] = True
    payload["passed"] = True
    artifacts["burn_in"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "battery_low=True" in check.detail


def test_production_readiness_recomputes_low_battery_from_burn_in_minimum(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["burn_in"].read_text())
    payload["min_battery_percent"] = 24
    payload["battery_low_seen"] = False
    payload["battery_critical_seen"] = False
    payload["passed"] = True
    artifacts["burn_in"].write_text(json.dumps(payload))

    sample_lines = []
    for raw_line in artifacts["burn_in_samples"].read_text().splitlines():
        sample = json.loads(raw_line)
        if sample["battery_percent"] == 62:
            sample["battery_percent"] = 24
        sample_lines.append(json.dumps(sample))
    artifacts["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "min_above_low=False(25%)" in check.detail


def test_production_readiness_rejects_burn_in_threshold_mismatch(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["burn_in"].read_text())
    payload["battery_low_percent"] = 15
    payload["thermal_critical_c"] = 90.0
    artifacts["burn_in"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "burn_in"][0]
    assert check.ok is False
    assert "thresholds_ok=False" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "disk_space" and not check.ok for check in report.checks)


def test_production_readiness_rejects_relative_state_path(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["BOX_STATE_PATH"] = "state.json"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "state_path"][0]
    assert check.ok is False
    assert "must be absolute" in check.detail


def test_production_readiness_rejects_missing_state_parent(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["BOX_STATE_PATH"] = str(tmp_path / "missing" / "state.json")

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "state_path"][0]
    assert check.ok is False
    assert "missing parent" in check.detail


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


def test_production_readiness_fails_without_systemd_service(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        service_unit_path=tmp_path / "missing.service",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "systemd_service"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_rejects_unsafe_systemd_service(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    bad_service = tmp_path / "deploy" / "systemd" / "bad.service"
    bad_service.parent.mkdir(parents=True, exist_ok=True)
    bad_service.write_text(
        "\n".join(
            [
                "[Service]",
                "Type=simple",
                "ExecStart=/usr/bin/env uv run boring box-run",
                "Restart=on-failure",
                "User=root",
                "",
                "[Install]",
                "WantedBy=default.target",
            ]
        )
    )

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        service_unit_path=bad_service,
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "systemd_service"][0]
    assert check.ok is False
    assert "Type=simple" in check.detail
    assert "WatchdogSec=-" in check.detail
    assert "User=root" in check.detail


def test_production_readiness_fails_without_systemd_runtime_report(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=tmp_path / "reports" / "missing-systemd-check.json",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "systemd_runtime"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_rejects_inactive_systemd_runtime(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["systemd"].read_text())
    payload["passed"] = False
    payload["active_state"] = "inactive"
    payload["sub_state"] = "dead"
    payload["failures"] = ["active=inactive", "sub=dead"]
    artifacts["systemd"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "systemd_runtime"][0]
    assert check.ok is False
    assert "active=inactive" in check.detail


def test_production_readiness_rejects_systemd_runtime_without_main_pid(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["systemd"].read_text())
    payload["main_pid"] = 0
    artifacts["systemd"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "systemd_runtime"][0]
    assert check.ok is False
    assert "main_pid=0" in check.detail


def test_production_readiness_fails_without_position_runtime_report(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=tmp_path / "reports" / "missing-position-check.json",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "position_runtime"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_rejects_wrong_position_runtime(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["position"].read_text())
    payload["passed"] = False
    payload["lat"] = 51.0
    payload["failures"] = ["lat_delta=0.362900"]
    artifacts["position"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "position_runtime"][0]
    assert check.ok is False
    assert "lat_delta=0.362900" in check.detail


def test_production_readiness_rejects_gpsd_position_for_other_endpoint(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["position"].read_text())
    payload["mode"] = "gpsd"
    payload["source"] = "gpsd"
    payload["gpsd_host"] = "gps-old.local"
    payload["gpsd_port"] = 2947
    artifacts["position"].write_text(json.dumps(payload))
    env = _ready_env()
    env["POSITION_MODE"] = "gpsd"
    env["GPSD_HOST"] = "gps-new.local"
    env["GPSD_PORT"] = "2948"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "position_runtime"][0]
    assert check.ok is False
    assert "gpsd=gps-old.local/gps-new.local:2947/2948" in check.detail


def test_production_readiness_fails_without_camera_runtime_report(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=tmp_path / "reports" / "missing-camera-check.json",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "camera_runtime"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_rejects_low_resolution_camera_runtime(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["camera"].read_text())
    payload["passed"] = False
    payload["width"] = 320
    payload["height"] = 240
    payload["failures"] = ["width=320/640", "height=240/480"]
    artifacts["camera"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "camera_runtime"][0]
    assert check.ok is False
    assert "resolution=320x240" in check.detail


def test_production_readiness_rejects_camera_below_hardware_profile_resolution(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    hardware = json.loads(artifacts["hardware"].read_text())
    hardware["camera"]["resolution"] = "1920x1080"
    artifacts["hardware"].write_text(json.dumps(hardware))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "camera_runtime"][0]
    assert check.ok is False
    assert "resolution=1280x720" in check.detail
    assert "profile_min=1920x1080" in check.detail


def test_production_readiness_fails_without_network_runtime_report(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=tmp_path / "reports" / "missing-network-check.json",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "network_runtime"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_rejects_offline_network_runtime(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["network"].read_text())
    payload["passed"] = False
    payload["online"] = False
    payload["failures"] = ["online=false"]
    artifacts["network"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "network_runtime"][0]
    assert check.ok is False
    assert "online=false" in check.detail


def test_production_readiness_rejects_network_runtime_for_other_recovery_command(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["network"].read_text())
    payload["recovery_command"] = "systemctl restart other-network"
    artifacts["network"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "network_runtime"][0]
    assert check.ok is False
    assert "systemctl restart other-network/systemctl restart NetworkManager" in check.detail


def test_production_readiness_rejects_network_runtime_for_other_timeout(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["network"].read_text())
    payload["timeout_seconds"] = 1.0
    artifacts["network"].write_text(json.dumps(payload))
    env = _ready_env()
    env["NETWORK_PROBE_TIMEOUT_SECONDS"] = "5"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "network_runtime"][0]
    assert check.ok is False
    assert "timeout=1.0/5.0s" in check.detail


def test_production_readiness_fails_without_power_runtime_report(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=tmp_path / "reports" / "missing-power-check.json",
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "power_runtime"][0]
    assert check.ok is False
    assert "missing" in check.detail


def test_production_readiness_rejects_critical_power_runtime(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["power"].read_text())
    payload["passed"] = False
    payload["battery_percent"] = 8
    payload["failures"] = ["battery_percent=8/10"]
    artifacts["power"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "power_runtime"][0]
    assert check.ok is False
    assert "battery=8%" in check.detail


def test_production_readiness_rejects_power_runtime_using_full_capacity(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["power"].read_text())
    payload["estimated_runtime_hours"] = 12.5
    artifacts["power"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "power_runtime"][0]
    assert check.ok is False
    assert "available=82.0/82.0Wh" in check.detail
    assert "runtime_consistent=False" in check.detail


def test_production_readiness_rejects_power_runtime_for_other_draw(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["power"].read_text())
    payload["estimated_draw_watts"] = 5
    payload["estimated_runtime_hours"] = 16.4
    artifacts["power"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "power_runtime"][0]
    assert check.ok is False
    assert "draw=5.0/8.0W" in check.detail


def test_production_readiness_rejects_power_runtime_for_other_required_runtime(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["power"].read_text())
    payload["required_runtime_hours"] = 8
    artifacts["power"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "power_runtime"][0]
    assert check.ok is False
    assert "required=8.0/10.0h" in check.detail


def test_production_readiness_rejects_power_runtime_for_other_critical_threshold(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["power"].read_text())
    payload["battery_critical_percent"] = 5
    artifacts["power"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "power_runtime"][0]
    assert check.ok is False
    assert "critical=5/10%" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "vision_eval" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_vision_eval_has_no_true_positives(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload["true_positives"] = 0
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_eval"][0]
    assert "true_positives=0" in check.detail


def test_production_readiness_recomputes_vision_eval_metrics_from_counts(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload["recall"] = 0.93
    payload["true_positives"] = 93
    payload["false_negatives"] = 93
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_eval"][0]
    assert check.ok is False
    assert "metrics_consistent=False" in check.detail


def test_production_readiness_fails_when_vision_eval_uses_other_model(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload["model_path"] = str(tmp_path / "models" / "other.pt")
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_eval"][0]
    assert check.ok is False
    assert "other.pt" in check.detail


def test_production_readiness_fails_when_vision_eval_uses_other_dataset(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    other_dataset = tmp_path / "datasets" / "other-control-vehicle"
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload["dataset_path"] = str(other_dataset)
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_eval"][0]
    assert check.ok is False
    assert "other-control-vehicle" in check.detail


def test_production_readiness_fails_when_vision_eval_uses_other_class(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["vision_eval"].read_text())
    payload["required_class"] = "car"
    artifacts["vision_eval"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_eval"][0]
    assert check.ok is False
    assert "class=car/control_vehicle" in check.detail


def test_production_readiness_fails_when_benchmark_fails(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, benchmark_passed=False, benchmark_fps=0.5)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    assert any(check.name == "vision_benchmark" and not check.ok for check in report.checks)


def test_production_readiness_fails_when_benchmark_has_no_detections(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["benchmark"].read_text())
    payload["detections_seen"] = 0
    payload["passed"] = True
    artifacts["benchmark"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_benchmark"][0]
    assert check.ok is False
    assert "detections=0" in check.detail


def test_production_readiness_fails_when_benchmark_uses_other_model(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["benchmark"].read_text())
    payload["model_path"] = str(tmp_path / "models" / "other.pt")
    artifacts["benchmark"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_benchmark"][0]
    assert check.ok is False
    assert "other.pt" in check.detail


def test_production_readiness_fails_when_benchmark_uses_other_target(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["benchmark"].read_text())
    payload["target_labels"] = ["car"]
    artifacts["benchmark"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "vision_benchmark"][0]
    assert check.ok is False
    assert "target=car/control_vehicle" in check.detail


def test_production_readiness_requires_benchmark_threshold_from_hardware_preset(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, benchmark_fps=2.5, benchmark_min_fps=1.0)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_requires_notification_test_for_exact_webhook(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["BORING_NOTIFY_WEBHOOK_URL"] = "https://notify.example.test/boring-v2"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "notification_test"][0]
    assert "hash=mismatch" in check.detail


def test_production_readiness_requires_low_battery_notification_message(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["notification"].read_text())
    payload["title"] = "Boring Box - test notification"
    payload["message"] = "Canal notification pret."
    artifacts["notification"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "notification_test"][0]
    assert "battery_message=False" in check.detail


def test_production_readiness_requires_timestamped_notification_test(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["notification"].read_text())
    payload.pop("tested_at")
    artifacts["notification"].write_text(json.dumps(payload))
    env = _ready_env()
    env["BOX_READINESS_MAX_REPORT_AGE_HOURS"] = "0"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "notification_test"][0]
    assert "tested_at=missing" in check.detail


def test_production_readiness_fails_when_autopay_smoke_fails(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path, autopay_smoke_passed=False)

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_rejects_missing_geofence_zones(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    env = _ready_env()
    env["PARKING_ZONES_PATH"] = str(tmp_path / "missing-zones.geojson")

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "autopay"][0]
    assert check.ok is False
    assert "geofence_zones" in check.detail


def test_production_readiness_rejects_incomplete_paybyphone_hints(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["endpoints"].read_text())
    payload["config_hints"]["payment_method_id"] = ""
    artifacts["endpoints"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "autopay"][0]
    assert check.ok is False
    assert "paybyphone_har_artifact" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_rejects_autopay_smoke_with_mismatched_session_zone(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["session_location_id"] = "zone-other"
    artifacts["autopay_smoke"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "session_zone=zone-other/zone-1" in check.detail


def test_production_readiness_rejects_autopay_smoke_above_session_limit(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["amount_cents"] = 650
    artifacts["autopay_smoke"].write_text(json.dumps(payload))
    env = _ready_env()
    env["MAX_SESSION_AMOUNT_CENTS"] = "500"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "amount=650/500" in check.detail


def test_production_readiness_rejects_autopay_smoke_for_other_duration(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["duration_minutes"] = 5
    artifacts["autopay_smoke"].write_text(json.dumps(payload))
    env = _ready_env()
    env["DEFAULT_DURATION_MINUTES"] = "15"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "duration=5/15" in check.detail


def test_production_readiness_rejects_autopay_smoke_for_other_position(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["autopay_smoke"].read_text())
    payload["lat"] = 48.8566
    payload["lon"] = 2.3522
    artifacts["autopay_smoke"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "position=48.85660,2.35220/50.63710,3.06330" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_rejects_stale_runtime_reports(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)
    payload = json.loads(artifacts["power"].read_text())
    payload["checked_at"] = (now - timedelta(hours=96)).isoformat()
    artifacts["power"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        now=now,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "power_runtime=96.0h>72.0h" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_rejects_runtime_report_without_timestamp(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    payload = json.loads(artifacts["camera"].read_text())
    payload.pop("checked_at")
    artifacts["camera"].write_text(json.dumps(payload))

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "camera_runtime=missing_timestamp" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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


def test_production_readiness_requires_runtime_event_log(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    artifacts["events"].unlink()

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path / "events.jsonl",
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "missing required" in check.detail


def test_production_readiness_uses_configured_event_log_path(tmp_path: Path):
    report_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=report_time)
    artifacts["events"].unlink()
    configured_events = tmp_path / "custom" / "events.jsonl"
    configured_events.parent.mkdir()
    configured_events.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2025-12-31T14:00:10+00:00",
                        "event": "heartbeat",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-01-01T00:00:00+00:00",
                        "event": "heartbeat",
                    }
                ),
            ]
        )
        + "\n"
    )
    env = _ready_env()
    env["BOX_EVENT_LOG_PATH"] = str(configured_events)
    env["BOX_READINESS_MAX_REPORT_AGE_HOURS"] = "0"

    report = audit_production_readiness(
        env=env,
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "scanned=2" in check.detail


def test_production_readiness_can_allow_missing_runtime_event_log_for_rehearsal(
    tmp_path: Path,
):
    artifacts = _write_ready_artifacts(tmp_path)
    artifacts["events"].unlink()

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=tmp_path / "events.jsonl",
        require_runtime_event_log=False,
    )

    assert report.passed is True
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is True
    assert "missing optional" in check.detail


def test_production_readiness_rejects_empty_runtime_event_log(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    artifacts["events"].write_text("")

    report = audit_production_readiness(
        env=_ready_env(),
        dataset_path=artifacts["dataset"],
        model_path=artifacts["model"],
        baseline_manifest=artifacts["manifest"],
        endpoints_path=artifacts["endpoints"],
        hardware_profile_path=artifacts["hardware"],
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=artifacts["events"],
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "scanned=0" in check.detail


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
        + json.dumps(
            {
                "ts": (now - timedelta(hours=10)).isoformat(),
                "event": "heartbeat",
            }
        )
        + "\n"
        + json.dumps(
            {
                "ts": now.isoformat(),
                "event": "heartbeat",
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
    assert "scanned=2" in check.detail
    assert "heartbeat=True" in check.detail


def test_production_readiness_rejects_runtime_log_without_heartbeat(tmp_path: Path):
    artifacts = _write_ready_artifacts(tmp_path)
    artifacts["events"].write_text(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "service_started",
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=artifacts["events"],
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "heartbeat=False" in check.detail


def test_production_readiness_rejects_stale_runtime_heartbeat(tmp_path: Path):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)
    artifacts["events"].write_text(
        json.dumps(
            {
                "ts": (now - timedelta(hours=1)).isoformat(),
                "event": "heartbeat",
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=artifacts["events"],
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "heartbeat_start_gap=32400s/1800s" in check.detail


def test_production_readiness_rejects_runtime_heartbeat_missing_start_coverage(
    tmp_path: Path,
):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)
    artifacts["events"].write_text(
        json.dumps(
            {
                "ts": now.isoformat(),
                "event": "heartbeat",
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=artifacts["events"],
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "heartbeat_start_gap=36000s/1800s" in check.detail


def test_production_readiness_rejects_runtime_heartbeat_missing_end_coverage(
    tmp_path: Path,
):
    now = datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)
    artifacts = _write_ready_artifacts(tmp_path, report_time=now)
    artifacts["events"].write_text(
        json.dumps(
            {
                "ts": (now - timedelta(hours=10)).isoformat(),
                "event": "heartbeat",
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
        vision_eval_report_path=artifacts["vision_eval"],
        benchmark_report_path=artifacts["benchmark"],
        autopay_smoke_report_path=artifacts["autopay_smoke"],
        notification_report_path=artifacts["notification"],
        burn_in_report_path=artifacts["burn_in"],
        storage_path=artifacts["events"],
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "runtime_event_log"][0]
    assert check.ok is False
    assert "heartbeat_end_gap=36000s/1800s" in check.detail


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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        systemd_report_path=artifacts["systemd"],
        position_report_path=artifacts["position"],
        camera_report_path=artifacts["camera"],
        network_report_path=artifacts["network"],
        power_report_path=artifacts["power"],
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
        "BOX_STATE_PATH": "/tmp/boring-state-readiness.json",
    }


def _write_ready_artifacts(
    tmp_path: Path,
    *,
    report_time: datetime | None = None,
    burn_in_hours: float = 10,
    include_edge: bool = True,
    charging_seen: bool = True,
    discharging_seen: bool = True,
    benchmark_passed: bool = True,
    benchmark_fps: float = 2.0,
    benchmark_min_fps: float = 2.0,
    notification_passed: bool = True,
    autopay_smoke_passed: bool = True,
    hardware_battery_wh: float = 100,
    hardware_charge_watts: float = 30,
    vision_eval_passed: bool = True,
    vision_recall: float = 0.93,
    vision_false_positive_per_hour: float = 1 / 3,
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
                    "url": f"https://example.test/control-vehicle/{index}.jpg",
                    "source": "web-search-candidates",
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
                    "image_id": f"openimages-{index}",
                    "source": "open-images",
                    "license_reviewed": True,
                    "license_status": "open-images",
                }
            )
        )
    manifest.write_text("\n".join(lines) + "\n")

    dataset = tmp_path / "datasets" / "control_vehicle_v1"
    train_dir = dataset / "train" / "images"
    valid_dir = dataset / "valid" / "images"
    train_label_dir = dataset / "train" / "labels"
    valid_label_dir = dataset / "valid" / "labels"
    train_dir.mkdir(parents=True)
    valid_dir.mkdir(parents=True)
    train_label_dir.mkdir(parents=True)
    valid_label_dir.mkdir(parents=True)
    (dataset / "data.yaml").write_text("names: ['control_vehicle']\n")
    for index in range(300):
        (train_dir / f"train-{index}.jpg").write_bytes(b"image")
        (train_label_dir / f"train-{index}.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    for index in range(50):
        (valid_dir / f"valid-{index}.jpg").write_bytes(b"image")
        (valid_label_dir / f"valid-{index}.txt").write_text("0 0.5 0.5 0.2 0.2\n")

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
                "dataset_path": str(dataset),
                "dataset_id": "field-pi5-daylight-v1",
                "required_class": "control_vehicle",
                "recall": vision_recall,
                "precision": 93 / 94,
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
    start_battery = 70
    end_battery = 82 if charging_seen else 62
    min_battery = 70 if charging_seen and not discharging_seen else 62
    battery_delta = end_battery - start_battery
    burn_in.write_text(
        json.dumps(
            {
                "passed": True,
                "started_at": report_time.timestamp() - burn_in_hours * 3600,
                "ended_at": report_time.timestamp(),
                "duration_seconds": burn_in_hours * 3600,
                "sample_count": int(burn_in_hours * 60),
                "camera_failures": 0,
                "network_failures": 0,
                "battery_critical_seen": False,
                "battery_low_percent": 25,
                "battery_critical_percent": 10,
                "thermal_warning_c": 75.0,
                "thermal_critical_c": 85.0,
                "thermal_critical_seen": False,
                "charging_seen": charging_seen,
                "discharging_seen": discharging_seen,
                "start_battery_percent": start_battery,
                "end_battery_percent": end_battery,
                "min_battery_percent": min_battery,
                "battery_delta_percent": battery_delta,
                "max_temp_c": 55.0,
            }
        )
    )
    burn_in_samples = burn_in.with_name("samples.jsonl")
    sample_count = int(burn_in_hours * 60)
    burn_in_sample_lines = []
    for index in range(sample_count):
        if index == 0:
            battery_percent = start_battery
        elif index == sample_count - 1:
            battery_percent = end_battery
        else:
            battery_percent = min_battery
        if charging_seen and discharging_seen:
            battery_charging = index >= sample_count // 2
        elif charging_seen:
            battery_charging = True
        elif discharging_seen:
            battery_charging = False
        else:
            battery_charging = None
        burn_in_sample_lines.append(
            json.dumps(
                {
                    "ts": report_time.timestamp() - burn_in_hours * 3600 + index * 60,
                    "camera_ok": True,
                    "camera_error": None,
                    "battery_percent": battery_percent,
                    "battery_charging": battery_charging,
                    "battery_source": "bat",
                    "temp_c": 55.0 if index == sample_count - 1 else 44.0,
                    "thermal_source": "thermal",
                    "thermal_label": "cpu",
                    "network_online": True,
                    "network_error": None,
                }
            )
        )
    burn_in_samples.write_text("\n".join(burn_in_sample_lines) + "\n")

    benchmark = tmp_path / "reports" / "vision-benchmark.json"
    benchmark.parent.mkdir(exist_ok=True)
    benchmark.write_text(
        json.dumps(
            {
                "model_path": str(model),
                "target_labels": ["control_vehicle"],
                "device": "cpu",
                "frames_processed": 120,
                "detections_seen": 12,
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
                "session_location_id": "zone-1",
                "session_id": "session-1",
                "amount_cents": 120 if autopay_smoke_passed else 0,
                "duration_minutes": 15,
                "lat": 50.6371,
                "lon": 3.0633,
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
                "webhook_hash": _hash("https://notify.example.test/boring"),
                "status_code": 204 if notification_passed else 500,
                "title": "Boring Box - test notification",
                "message": "Canal notification pret pour batterie faible.",
                "tested_at": report_time_iso,
                "error": None if notification_passed else "HTTP 500",
            }
        )
    )

    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "ts": (report_time - timedelta(hours=burn_in_hours)).isoformat(),
                "event": "heartbeat",
                "model_path": str(model),
                "payment_dry_run": False,
            }
        )
        + "\n"
        + json.dumps(
            {
                "ts": report_time.isoformat(),
                "event": "heartbeat",
                "model_path": str(model),
                "payment_dry_run": False,
            }
        )
        + "\n"
    )

    systemd = tmp_path / "reports" / "systemd-check.json"
    systemd.write_text(
        json.dumps(
            {
                "service": "boring-box.service",
                "passed": True,
                "enabled_state": "enabled",
                "active_state": "active",
                "sub_state": "running",
                "unit_file_state": "enabled",
                "type": "notify",
                "watchdog_usec": 30_000_000,
                "main_pid": 1234,
                "exec_start": "/opt/boring/.venv/bin/boring box-run",
                "user": "boring",
                "checked_at": report_time_iso,
                "failures": [],
                "error": None,
            }
        )
    )

    position = tmp_path / "reports" / "position-check.json"
    position.write_text(
        json.dumps(
            {
                "passed": True,
                "mode": "static",
                "source": "static",
                "lat": 50.6371,
                "lon": 3.0633,
                "gpsd_host": None,
                "gpsd_port": None,
                "checked_at": report_time_iso,
                "failures": [],
            }
        )
    )

    camera = tmp_path / "reports" / "camera-check.json"
    camera.write_text(
        json.dumps(
            {
                "passed": True,
                "device_index": 0,
                "width": 1280,
                "height": 720,
                "min_width": 640,
                "min_height": 480,
                "checked_at": report_time_iso,
                "failures": [],
                "error": None,
            }
        )
    )

    network = tmp_path / "reports" / "network-check.json"
    network.write_text(
        json.dumps(
            {
                "passed": True,
                "target": "1.1.1.1:443",
                "online": True,
                "timeout_seconds": 3.0,
                "recovery_command_configured": True,
                "recovery_command": "systemctl restart NetworkManager",
                "checked_at": report_time_iso,
                "failures": [],
                "error": None,
            }
        )
    )

    power = tmp_path / "reports" / "power-check.json"
    power.write_text(
        json.dumps(
            {
                "passed": True,
                "battery_percent": 82,
                "charging": False,
                "source": "/sys/class/power_supply/BAT0",
                "battery_capacity_wh": hardware_battery_wh,
                "available_battery_wh": hardware_battery_wh * 0.82,
                "estimated_draw_watts": 8.0,
                "estimated_runtime_hours": (hardware_battery_wh * 0.82) / 8.0,
                "required_runtime_hours": 10.0,
                "battery_critical_percent": 10,
                "checked_at": report_time_iso,
                "failures": [],
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
        "burn_in_samples": burn_in_samples,
        "events": events,
        "systemd": systemd,
        "position": position,
        "camera": camera,
        "network": network,
        "power": power,
    }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
