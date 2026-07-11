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


def test_default_evidence_paths_include_box_ready():
    paths = default_evidence_paths()

    assert paths["box_ready"] == Path("reports/box-readiness.json")
    assert paths["autopay_smoke"] == Path("reports/autopay-smoke.json")


def _write_evidence(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "box_ready": tmp_path / "reports" / "box-readiness.json",
        "hardware_profile": tmp_path / "deploy" / "pi" / "hardware-profile.json",
        "vision_eval": tmp_path / "reports" / "vision-eval.json",
        "vision_benchmark": tmp_path / "reports" / "vision-benchmark.json",
        "autopay_smoke": tmp_path / "reports" / "autopay-smoke.json",
        "notification_test": tmp_path / "reports" / "notification-test.json",
        "burn_in": tmp_path / "burn-in" / "report.json",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"passed": True}))
    paths["hardware_profile"].write_text(json.dumps({"board": {"model": "raspberry-pi-5"}}))
    return paths
