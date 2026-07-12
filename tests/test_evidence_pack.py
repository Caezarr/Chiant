from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
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
    assert vision_eval.passed is False
    assert "model=missing" in vision_eval.detail


def test_evidence_pack_requires_complete_vision_eval(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_eval"][0]
    assert item.passed is True
    assert "frames=10800" in item.detail
    assert "invalid=0" in item.detail
    assert "model=ok" in item.detail
    assert "dataset=ok" in item.detail


def test_evidence_pack_requires_complete_hardware_profile(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "hardware_profile"][0]
    assert item.passed is True
    assert "preset=pi5-production" in item.detail
    assert "board=raspberry-pi-5" in item.detail
    assert "checks=ok" in item.detail


def test_evidence_pack_requires_complete_box_ready_report(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "box_ready"][0]
    assert item.passed is True
    assert "checks=22" in item.detail
    assert "generated_at=ok" in item.detail
    assert "missing=-" in item.detail
    assert "failed=-" in item.detail


def test_evidence_pack_rejects_box_ready_without_generated_at(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["box_ready"].read_text())
    payload.pop("generated_at")
    paths["box_ready"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "box_ready"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "generated_at=missing" in item.detail


def test_evidence_pack_rejects_box_ready_without_checks(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["box_ready"].write_text(json.dumps({"passed": True}))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "box_ready"][0]
    assert pack.passed is False
    assert item.passed is False
    assert item.detail == "checks=missing"


def test_evidence_pack_rejects_box_ready_with_failed_required_check(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["box_ready"].read_text())
    check = [check for check in payload["checks"] if check["name"] == "autopay_smoke"][0]
    check["ok"] = False
    check["detail"] = "missing reports/autopay-smoke.json"
    paths["box_ready"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "box_ready"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "failed=autopay_smoke" in item.detail


def test_evidence_pack_rejects_box_ready_missing_required_check(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["box_ready"].read_text())
    payload["checks"] = [
        check for check in payload["checks"] if check["name"] != "runtime_event_log"
    ]
    paths["box_ready"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "box_ready"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "missing=runtime_event_log" in item.detail


def test_evidence_pack_requires_complete_runtime_reports(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    for name in [
        "systemd_runtime",
        "position_runtime",
        "camera_runtime",
        "network_runtime",
        "power_runtime",
        "burn_in",
    ]:
        item = [item for item in pack.items if item.name == name][0]
        assert item.passed is True
        assert "failures=-" in item.detail


def test_evidence_pack_recomputes_report_freshness(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)

    pack = build_evidence_pack(paths, max_report_age_hours=72, now=now)

    item = [item for item in pack.items if item.name == "report_freshness"][0]
    assert pack.passed is True
    assert item.passed is True
    assert "max_age=72.0h" in item.detail
    assert "box_ready=24.0h" in item.detail
    assert "autopay_smoke=24.0h" in item.detail
    assert "burn_in=14.0h" in item.detail
    assert "failures=-" in item.detail


def test_evidence_pack_rejects_stale_report_freshness(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    now = datetime(2026, 1, 6, tzinfo=timezone.utc)

    pack = build_evidence_pack(paths, max_report_age_hours=72, now=now)

    item = [item for item in pack.items if item.name == "report_freshness"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "box_ready=120.0h>72.0h" in item.detail
    assert "autopay_smoke=120.0h>72.0h" in item.detail


def test_evidence_pack_rejects_box_ready_freshness_without_timestamp(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["box_ready"].read_text())
    payload.pop("generated_at")
    paths["box_ready"].write_text(json.dumps(payload))

    pack = build_evidence_pack(
        paths,
        max_report_age_hours=72,
        now=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    item = [item for item in pack.items if item.name == "report_freshness"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "box_ready=missing_timestamp" in item.detail


def test_evidence_pack_rejects_autopay_freshness_without_timestamp(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["autopay_smoke"].read_text())
    payload.pop("tested_at")
    paths["autopay_smoke"].write_text(json.dumps(payload))

    pack = build_evidence_pack(
        paths,
        max_report_age_hours=72,
        now=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    item = [item for item in pack.items if item.name == "report_freshness"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "autopay_smoke=missing_timestamp" in item.detail


def test_evidence_pack_rejects_power_report_using_full_capacity_runtime(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["power_runtime"].read_text())
    payload["estimated_runtime_hours"] = 12.5
    paths["power_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "power_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "runtime_consistency" in item.detail


def test_evidence_pack_requires_power_runtime_critical_threshold(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["power_runtime"].read_text())
    payload.pop("battery_critical_percent")
    paths["power_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "power_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "battery_critical_percent" in item.detail


def test_evidence_pack_rejects_critical_power_runtime_battery(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["power_runtime"].read_text())
    payload["battery_percent"] = 10
    payload["available_battery_wh"] = 10
    payload["estimated_runtime_hours"] = 1.25
    payload["passed"] = True
    paths["power_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "power_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "battery_percent_critical" in item.detail


def test_evidence_pack_requires_runtime_events_to_cover_burn_in_window(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "runtime_alignment"][0]
    assert item.format == "derived"
    assert item.passed is True
    assert "heartbeat_start_gap=0s/1800s" in item.detail
    assert "heartbeat_end_gap=0s/1800s" in item.detail


def test_evidence_pack_rejects_runtime_events_without_burn_in_end_heartbeat(
    tmp_path: Path,
):
    paths = _write_evidence(tmp_path)
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "heartbeat"}) + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "runtime_alignment"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "heartbeat_end_gap=36000s/1800s" in item.detail


def test_evidence_pack_rejects_blocking_runtime_event_during_burn_in_window(
    tmp_path: Path,
):
    paths = _write_evidence(tmp_path)
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "heartbeat"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T02:00:00+00:00", "event": "network_offline"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T10:00:00+00:00", "event": "heartbeat"})
        + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "runtime_alignment"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "blocking=network_offline@line2" in item.detail


def test_evidence_pack_rejects_generic_camera_report(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["camera_runtime"].write_text(json.dumps({"passed": True}))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "camera_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "width" in item.detail
    assert "height" in item.detail


def test_evidence_pack_rejects_runtime_report_with_failures(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["network_runtime"].read_text())
    payload["passed"] = True
    payload["failures"] = ["online=false"]
    paths["network_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "network_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "failures=failures" in item.detail


def test_evidence_pack_rejects_gpsd_position_without_endpoint(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["position_runtime"].read_text())
    payload["mode"] = "gpsd"
    payload["source"] = "gpsd"
    payload["gpsd_host"] = ""
    payload["gpsd_port"] = None
    paths["position_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "position_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "gpsd_host" in item.detail
    assert "gpsd_port" in item.detail


def test_evidence_pack_rejects_systemd_runtime_without_main_pid(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["systemd_runtime"].read_text())
    payload["main_pid"] = 0
    paths["systemd_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "systemd_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "main_pid" in item.detail


def test_evidence_pack_rejects_network_report_without_recovery_command(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["network_runtime"].read_text())
    payload.pop("recovery_command")
    paths["network_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "network_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "recovery_command" in item.detail


def test_evidence_pack_rejects_network_report_without_timeout(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["network_runtime"].read_text())
    payload.pop("timeout_seconds")
    paths["network_runtime"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "network_runtime"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "timeout" in item.detail


def test_evidence_pack_rejects_burn_in_without_charge_cycle(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["burn_in"].read_text())
    payload["charging_seen"] = False
    paths["burn_in"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "charging_seen" in item.detail


def test_evidence_pack_rejects_low_battery_burn_in(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["burn_in"].read_text())
    payload["battery_low_seen"] = True
    paths["burn_in"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "battery_low" in item.detail


def test_evidence_pack_recomputes_low_battery_from_burn_in_minimum(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["burn_in"].read_text())
    payload["min_battery_percent"] = 24
    payload["battery_low_seen"] = False
    payload["battery_critical_seen"] = False
    paths["burn_in"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "min_battery_low" in item.detail


def test_evidence_pack_requires_burn_in_threshold_provenance(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["burn_in"].read_text())
    payload.pop("battery_low_percent")
    payload.pop("thermal_critical_c")
    paths["burn_in"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "battery_low_percent" in item.detail
    assert "thermal_critical_c" in item.detail


def test_evidence_pack_recomputes_burn_in_threshold_flags(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["burn_in"].read_text())
    payload["max_temp_c"] = 80.0
    payload["thermal_warning_seen"] = False
    paths["burn_in"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "thermal_warning_threshold_mismatch" in item.detail


def test_evidence_pack_rejects_hardware_profile_without_preset(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["hardware_profile"].read_text())
    del payload["preset_id"]
    paths["hardware_profile"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "hardware_profile"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "preset=-" in item.detail
    assert "checks=hardware_preset" in item.detail


def test_evidence_pack_rejects_hardware_profile_without_vehicle_charge(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["hardware_profile"].read_text())
    payload["power"]["vehicle_charge_watts"] = 0
    paths["hardware_profile"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "hardware_profile"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "vehicle_charge=-" in item.detail
    assert "hardware_preset" in item.detail
    assert "power_hardware" in item.detail


def test_evidence_pack_rejects_vision_eval_without_frames(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_eval"].read_text())
    payload["frames_evaluated"] = 0
    paths["vision_eval"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_eval"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "frames=0" in item.detail


def test_evidence_pack_rejects_vision_eval_with_invalid_images(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_eval"].read_text())
    payload["invalid_images"] = 1
    paths["vision_eval"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_eval"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "invalid=1" in item.detail


def test_evidence_pack_rejects_vision_eval_without_true_positives(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_eval"].read_text())
    payload["true_positives"] = 0
    paths["vision_eval"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_eval"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "true_positives=0" in item.detail


def test_evidence_pack_recomputes_vision_eval_metrics_from_counts(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_eval"].read_text())
    payload["recall"] = 0.93
    payload["true_positives"] = 93
    payload["false_negatives"] = 93
    paths["vision_eval"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_eval"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "metrics_consistent=False" in item.detail


def test_evidence_pack_rejects_vision_eval_for_other_class(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_eval"].read_text())
    payload["required_class"] = "car"
    paths["vision_eval"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_eval"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "class=car/control_vehicle" in item.detail


def test_evidence_pack_requires_complete_vision_benchmark(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_benchmark"][0]
    assert item.passed is True
    assert "fps=2.00/2.00" in item.detail
    assert "frames=120" in item.detail
    assert "detections=12" in item.detail
    assert "device=ok" in item.detail

    alignment = [item for item in pack.items if item.name == "hardware_benchmark_alignment"][0]
    assert alignment.passed is True
    assert "measured_fps=2.00/2.00" in alignment.detail
    assert "benchmark_min_fps=2.00/2.00" in alignment.detail

    model_alignment = [item for item in pack.items if item.name == "vision_model_alignment"][0]
    assert model_alignment.passed is True
    assert "same_model=True" in model_alignment.detail


def test_evidence_pack_rejects_vision_benchmark_from_other_model(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_benchmark"].read_text())
    payload["model_path"] = "models/other.pt"
    paths["vision_benchmark"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    alignment = [item for item in pack.items if item.name == "vision_model_alignment"][0]
    assert pack.passed is False
    assert alignment.passed is False
    assert "eval_model=models/best.pt" in alignment.detail
    assert "benchmark_model=models/other.pt" in alignment.detail
    assert "same_model=False" in alignment.detail


def test_evidence_pack_rejects_benchmark_below_hardware_profile_target(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_benchmark"].read_text())
    payload["min_fps"] = 1.0
    payload["measured_fps"] = 1.5
    paths["vision_benchmark"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    alignment = [item for item in pack.items if item.name == "hardware_benchmark_alignment"][0]
    assert pack.passed is False
    assert alignment.passed is False
    assert "measured_fps=1.50/2.00" in alignment.detail
    assert "benchmark_min_fps=1.00/2.00" in alignment.detail


def test_evidence_pack_rejects_benchmark_minimum_below_hardware_profile_target(
    tmp_path: Path,
):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_benchmark"].read_text())
    payload["min_fps"] = 1.0
    payload["measured_fps"] = 2.0
    paths["vision_benchmark"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    alignment = [item for item in pack.items if item.name == "hardware_benchmark_alignment"][0]
    assert pack.passed is False
    assert alignment.passed is False
    assert "measured_fps=2.00/2.00" in alignment.detail
    assert "benchmark_min_fps=1.00/2.00" in alignment.detail


def test_evidence_pack_rejects_slow_vision_benchmark(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_benchmark"].read_text())
    payload["measured_fps"] = 1.0
    paths["vision_benchmark"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_benchmark"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "fps=1.00/2.00" in item.detail


def test_evidence_pack_rejects_vision_benchmark_without_detections(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_benchmark"].read_text())
    payload["detections_seen"] = 0
    payload["passed"] = True
    paths["vision_benchmark"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_benchmark"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "detections=0" in item.detail


def test_evidence_pack_rejects_vision_benchmark_for_other_target(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["vision_benchmark"].read_text())
    payload["target_labels"] = ["car"]
    paths["vision_benchmark"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "vision_benchmark"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "target=car/control_vehicle" in item.detail


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
    assert "session_zone=zone-1/zone-1" in item.detail


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


def test_evidence_pack_rejects_autopay_smoke_with_mismatched_session_zone(
    tmp_path: Path,
):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["autopay_smoke"].read_text())
    payload["session_location_id"] = "zone-other"
    paths["autopay_smoke"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "autopay_smoke"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "session_zone=zone-other/zone-1" in item.detail


def test_evidence_pack_requires_complete_notification_test(tmp_path: Path):
    paths = _write_evidence(tmp_path)

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "notification_test"][0]
    assert item.passed is True
    assert "status=204" in item.detail
    assert "host=ok" in item.detail
    assert "hash=ok" in item.detail


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


def test_evidence_pack_rejects_notification_test_without_hash(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["notification_test"].read_text())
    payload["webhook_hash"] = ""
    paths["notification_test"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "notification_test"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "hash=missing" in item.detail


def test_evidence_pack_rejects_notification_test_without_low_battery_message(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    payload = json.loads(paths["notification_test"].read_text())
    payload["message"] = "Canal notification pret."
    paths["notification_test"].write_text(json.dumps(payload))

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "notification_test"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "battery_message=False" in item.detail


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
    assert "scanned=600/600" in item.detail
    assert "start_battery=90.00/90.00" in item.detail
    assert "end_battery=68.00/68.00" in item.detail
    assert "battery_delta=-22.00/-22.00" in item.detail
    assert "charging_seen=True/True" in item.detail
    assert "discharging_seen=True/True" in item.detail
    assert "timestamps_monotonic=True" in item.detail
    assert "timestamps_in_window=True" in item.detail


def test_evidence_pack_rejects_burn_in_sample_camera_failure(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["burn_in_samples"].write_text(
        json.dumps(
            {
                "ts": 1.0,
                "camera_ok": False,
                "network_online": True,
                "battery_percent": 90,
                "battery_charging": True,
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


def test_evidence_pack_rejects_burn_in_samples_charge_cycle_mismatch(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    sample_lines = []
    for raw_line in paths["burn_in_samples"].read_text().splitlines():
        payload = json.loads(raw_line)
        payload["battery_charging"] = True
        sample_lines.append(json.dumps(payload))
    paths["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "discharging_seen=False/True" in item.detail


def test_evidence_pack_rejects_burn_in_samples_outside_report_window(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    sample_lines = []
    for raw_line in paths["burn_in_samples"].read_text().splitlines():
        payload = json.loads(raw_line)
        payload["ts"] = "2025-12-31T23:00:00+00:00"
        sample_lines.append(json.dumps(payload))
    paths["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "timestamps_in_window=False" in item.detail


def test_evidence_pack_rejects_non_monotonic_burn_in_samples(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    sample_lines = []
    for line_number, raw_line in enumerate(paths["burn_in_samples"].read_text().splitlines()):
        payload = json.loads(raw_line)
        if line_number == 1:
            payload["ts"] = "2026-01-01T10:00:00+00:00"
        sample_lines.append(json.dumps(payload))
    paths["burn_in_samples"].write_text("\n".join(sample_lines) + "\n")

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "timestamps_monotonic=False" in item.detail


def test_evidence_pack_rejects_burn_in_samples_without_power_metrics(tmp_path: Path):
    paths = _write_evidence(tmp_path)
    paths["burn_in_samples"].write_text(
        json.dumps(
            {
                "ts": 1.0,
                "camera_ok": True,
                "network_online": True,
                "battery_percent": None,
                "battery_charging": True,
                "temp_c": None,
            }
        )
        + "\n"
    )

    pack = build_evidence_pack(paths)

    item = [item for item in pack.items if item.name == "burn_in_samples"][0]
    assert pack.passed is False
    assert item.passed is False
    assert "start_battery=-/90.00" in item.detail
    assert "max_temp=-/56.00" in item.detail


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
    paths["box_ready"].write_text(json.dumps(_box_ready_payload()))
    paths["camera_runtime"].write_text(json.dumps(_camera_runtime_payload()))
    paths["position_runtime"].write_text(json.dumps(_position_runtime_payload()))
    paths["network_runtime"].write_text(json.dumps(_network_runtime_payload()))
    paths["power_runtime"].write_text(json.dumps(_power_runtime_payload()))
    paths["systemd_runtime"].write_text(json.dumps(_systemd_runtime_payload()))
    paths["burn_in"].write_text(json.dumps(_burn_in_payload()))
    paths["vision_eval"].write_text(
        json.dumps(
            {
                "passed": True,
                "model_path": "models/best.pt",
                "dataset_path": "datasets/control_vehicle_v1",
                "dataset_id": "field-pi5-daylight-v1",
                "required_class": "control_vehicle",
                "recall": 0.93,
                "min_recall": 0.9,
                "precision": 93 / 94,
                "false_positive_per_hour": 1 / 3,
                "max_false_positive_per_hour": 1.0,
                "evaluated_hours": 3.0,
                "frames_evaluated": 10_800,
                "true_positives": 93,
                "false_positives": 1,
                "false_negatives": 7,
                "invalid_images": 0,
                "generated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    paths["vision_benchmark"].write_text(
        json.dumps(
            {
                "passed": True,
                "model_path": "models/best.pt",
                "target_labels": ["control_vehicle"],
                "device": "cpu",
                "frames_processed": 120,
                "detections_seen": 12,
                "duration_seconds": 60.0,
                "measured_fps": 2.0,
                "min_fps": 2.0,
                "generated_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )
    paths["autopay_smoke"].write_text(
        json.dumps(
            {
                "passed": True,
                "provider": "paybyphone",
                "dry_run": False,
                "plate": "AB-123-CD",
                "zone_id": "zone-1",
                "session_location_id": "zone-1",
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
                "webhook_hash": _hash("https://notify.example.test/boring"),
                "status_code": 204,
                "title": "Boring Box - test notification",
                "message": "Canal notification pret pour batterie faible.",
                "tested_at": "2026-01-01T00:00:00+00:00",
                "error": None,
            }
        )
    )
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "heartbeat"})
        + "\n"
        + json.dumps({"ts": "2026-01-01T10:00:00+00:00", "event": "heartbeat"})
        + "\n"
    )
    paths["burn_in_samples"].write_text(_burn_in_sample_lines())
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
    paths["hardware_profile"].write_text(
        json.dumps(
            {
                "profile_id": "pi5-test-001",
                "preset_id": "pi5-production",
                "board": {"model": "raspberry-pi-5", "ram_gb": 8},
                "camera": {"type": "usb-uvc", "device": "/dev/video0"},
                "storage": {"capacity_gb": 64, "endurance": True},
                "power": {
                    "ups_power_supply": True,
                    "battery_capacity_wh": 100,
                    "vehicle_charge_watts": 30,
                },
                "network": {"mode": "hotspot"},
                "runtime": {"detection_fps": 2.0, "min_benchmark_fps": 2.0},
            }
        )
    )
    return paths


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _box_ready_payload() -> dict:
    check_names = [
        "vision",
        "autopay",
        "autopay_smoke",
        "hardware",
        "hardware_env_consistency",
        "systemd_service",
        "systemd_runtime",
        "position_runtime",
        "camera_runtime",
        "network_runtime",
        "power_runtime",
        "vision_eval",
        "vision_benchmark",
        "power_budget",
        "network_recovery",
        "notification_webhook",
        "notification_test",
        "disk_space",
        "burn_in",
        "burn_in_samples",
        "runtime_event_log",
        "report_freshness",
    ]
    return {
        "passed": True,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "checks": [{"name": name, "ok": True, "detail": "ok"} for name in check_names],
    }


def _camera_runtime_payload() -> dict:
    return {
        "passed": True,
        "device_index": 0,
        "width": 1280,
        "height": 720,
        "min_width": 640,
        "min_height": 480,
        "checked_at": "2026-01-01T00:00:00+00:00",
        "failures": [],
        "error": None,
    }


def _position_runtime_payload() -> dict:
    return {
        "passed": True,
        "mode": "static",
        "source": "static",
        "lat": 50.6371,
        "lon": 3.0633,
        "gpsd_host": None,
        "gpsd_port": None,
        "checked_at": "2026-01-01T00:00:00+00:00",
        "failures": [],
    }


def _network_runtime_payload() -> dict:
    return {
        "passed": True,
        "target": "1.1.1.1:443",
        "online": True,
        "timeout_seconds": 3.0,
        "recovery_command_configured": True,
        "recovery_command": "systemctl restart NetworkManager",
        "checked_at": "2026-01-01T00:00:00+00:00",
        "failures": [],
        "error": None,
    }


def _power_runtime_payload() -> dict:
    return {
        "passed": True,
        "battery_percent": 82,
        "charging": False,
        "source": "/sys/class/power_supply/BAT0",
        "battery_capacity_wh": 100,
        "available_battery_wh": 82,
        "estimated_draw_watts": 8,
        "estimated_runtime_hours": 10.25,
        "required_runtime_hours": 10,
        "battery_critical_percent": 10,
        "checked_at": "2026-01-01T00:00:00+00:00",
        "failures": [],
    }


def _systemd_runtime_payload() -> dict:
    return {
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
        "checked_at": "2026-01-01T00:00:00+00:00",
        "failures": [],
        "error": None,
    }


def _burn_in_payload() -> dict:
    return {
        "passed": True,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": "2026-01-01T10:00:00+00:00",
        "duration_seconds": 36_000,
        "sample_count": 600,
        "camera_failures": 0,
        "network_failures": 0,
        "start_battery_percent": 90,
        "end_battery_percent": 68,
        "min_battery_percent": 68,
        "battery_delta_percent": -22,
        "charging_seen": True,
        "discharging_seen": True,
        "battery_low_percent": 25,
        "battery_critical_percent": 10,
        "thermal_warning_c": 75.0,
        "thermal_critical_c": 85.0,
        "max_temp_c": 56.0,
        "thermal_warning_seen": False,
        "thermal_critical_seen": False,
        "battery_low_seen": False,
        "battery_critical_seen": False,
    }


def _burn_in_sample_lines() -> str:
    lines = []
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(600):
        if index == 0:
            battery_percent = 90
        else:
            battery_percent = 68
        lines.append(
            json.dumps(
                {
                    "ts": (started_at + timedelta(minutes=index)).isoformat(),
                    "camera_ok": True,
                    "network_online": True,
                    "battery_percent": battery_percent,
                    "battery_charging": index < 300,
                    "temp_c": 56.0 if index == 599 else 44.0,
                }
            )
        )
    return "\n".join(lines) + "\n"
