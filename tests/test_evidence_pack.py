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
        "autopay_smoke": tmp_path / "reports" / "autopay-smoke.json",
        "notification_test": tmp_path / "reports" / "notification-test.json",
        "burn_in": tmp_path / "burn-in" / "report.json",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"passed": True}))
    paths["runtime_events"].write_text(
        json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": "heartbeat"}) + "\n"
    )
    paths["hardware_profile"].write_text(json.dumps({"board": {"model": "raspberry-pi-5"}}))
    return paths
