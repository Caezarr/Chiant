from __future__ import annotations

import json
from pathlib import Path

from boring.vision_readiness import audit_vision_readiness, write_report


def test_audit_vision_readiness_passes_with_expected_artifacts(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3)
    dataset = _write_dataset(tmp_path, train=2, valid=1, names="names: ['control_vehicle']")
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")

    report = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=2,
        min_negative_candidates=3,
        min_train_images=2,
        min_valid_images=1,
    )

    assert report.passed is True
    assert all(check.ok for check in report.checks)


def test_audit_vision_readiness_fails_without_required_class(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3)
    dataset = _write_dataset(tmp_path, train=2, valid=1, names="names: ['car']")
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")

    report = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=2,
        min_negative_candidates=3,
        min_train_images=2,
        min_valid_images=1,
    )

    assert report.passed is False
    assert any(check.name == "yolo_dataset" and not check.ok for check in report.checks)


def test_audit_vision_readiness_fails_with_unreviewed_sources(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3, license_reviewed=False)
    dataset = _write_dataset(tmp_path, train=2, valid=1, names="names: ['control_vehicle']")
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")

    strict = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=2,
        min_negative_candidates=3,
        min_train_images=2,
        min_valid_images=1,
    )
    rehearsal = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=2,
        min_negative_candidates=3,
        min_train_images=2,
        min_valid_images=1,
        require_license_review=False,
    )

    assert strict.passed is False
    assert any(check.name == "baseline_license_review" and not check.ok for check in strict.checks)
    assert rehearsal.passed is True


def test_audit_vision_readiness_can_require_edge_export(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=1, negatives=1)
    dataset = _write_dataset(tmp_path, train=1, valid=1, names="names:\n  0: control_vehicle")
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")

    missing = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=1,
        min_negative_candidates=1,
        min_train_images=1,
        min_valid_images=1,
        require_edge_export=True,
    )
    assert missing.passed is False

    (model.parent / "best.onnx").write_bytes(b"edge")
    ready = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=1,
        min_negative_candidates=1,
        min_train_images=1,
        min_valid_images=1,
        require_edge_export=True,
    )
    assert ready.passed is True


def test_write_report_includes_passed(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=1, negatives=1)
    dataset = _write_dataset(tmp_path, train=1, valid=1, names="names: ['control_vehicle']")
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")
    report = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        min_positive_candidates=1,
        min_negative_candidates=1,
        min_train_images=1,
        min_valid_images=1,
    )
    output = tmp_path / "reports" / "vision.json"

    write_report(report, output)

    payload = json.loads(output.read_text())
    assert payload["passed"] is True


def _write_manifest(
    tmp_path: Path,
    *,
    positives: int,
    negatives: int,
    license_reviewed: bool = True,
) -> Path:
    manifest = tmp_path / "datasets" / "baseline" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    lines = []
    for index in range(positives):
        lines.append(
            json.dumps(
                {
                    "profile": "positives",
                    "path": f"p{index}.jpg",
                    "license_reviewed": license_reviewed,
                    "license_status": "cc-by" if license_reviewed else "unknown",
                }
            )
        )
    for index in range(negatives):
        lines.append(
            json.dumps(
                {
                    "profile": "negatives",
                    "path": f"n{index}.jpg",
                    "license_reviewed": license_reviewed,
                    "license_status": "open-images" if license_reviewed else "unknown",
                }
            )
        )
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def _write_dataset(tmp_path: Path, *, train: int, valid: int, names: str) -> Path:
    dataset = tmp_path / "datasets" / "control_vehicle_v1"
    train_dir = dataset / "train" / "images"
    valid_dir = dataset / "valid" / "images"
    train_dir.mkdir(parents=True)
    valid_dir.mkdir(parents=True)
    (dataset / "data.yaml").write_text(names + "\n")
    for index in range(train):
        (train_dir / f"train-{index}.jpg").write_bytes(b"image")
    for index in range(valid):
        (valid_dir / f"valid-{index}.jpg").write_bytes(b"image")
    return dataset
