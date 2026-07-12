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


def test_audit_vision_readiness_fails_without_positive_labels(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3)
    dataset = _write_dataset(
        tmp_path,
        train=2,
        valid=1,
        names="names: ['control_vehicle']",
        write_labels=False,
    )
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
    check = [check for check in report.checks if check.name == "yolo_dataset"][0]
    assert check.ok is False
    assert "train_positive_labels=0/1" in check.detail
    assert "valid_positive_labels=0/1" in check.detail


def test_audit_vision_readiness_requires_enough_positive_label_coverage(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=200, negatives=500)
    dataset = _write_dataset(
        tmp_path,
        train=300,
        valid=50,
        names="names: ['control_vehicle']",
        train_positive_labels=1,
        valid_positive_labels=1,
    )
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")

    report = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
    )

    assert report.passed is False
    check = [check for check in report.checks if check.name == "yolo_dataset"][0]
    assert check.ok is False
    assert "train_positive_labels=1/60" in check.detail
    assert "valid_positive_labels=1/10" in check.detail


def test_audit_vision_readiness_fails_with_invalid_yolo_labels(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3)
    dataset = _write_dataset(tmp_path, train=2, valid=1, names="names: ['control_vehicle']")
    (dataset / "train" / "labels" / "train-0.txt").write_text("0 1.2 0.5 0.2 0.2\n")
    (dataset / "train" / "labels" / "train-1.txt").write_text("3 0.5 0.5 0.2 0.2\n")
    (dataset / "valid" / "labels" / "valid-0.txt").write_text("0.5 0.5 0.5 0.2 0.2\n")
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
    check = [check for check in report.checks if check.name == "yolo_dataset"][0]
    assert check.ok is False
    assert "invalid_labels=3" in check.detail


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


def test_audit_vision_readiness_fails_without_manifest_source_trace(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3, include_trace=False)
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

    assert report.passed is False
    check = [check for check in report.checks if check.name == "baseline_source_trace"][0]
    assert check.ok is False
    assert "missing_source=5" in check.detail
    assert "missing_locator=5" in check.detail


def test_audit_vision_readiness_fails_without_enough_free_sources(tmp_path: Path):
    manifest = _write_manifest(tmp_path, positives=2, negatives=3)
    dataset = _write_dataset(tmp_path, train=2, valid=1, names="names: ['control_vehicle']")
    catalog = tmp_path / "sources.json"
    catalog.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "id": "video-only",
                        "name": "video-only",
                        "url": "manual",
                        "usage": ["positives"],
                        "free": True,
                        "license_status": "copyright-risk",
                        "train_policy": "validation-only-do-not-train",
                        "action": "do not train",
                    }
                ],
            }
        )
    )
    model = tmp_path / "models" / "best.pt"
    model.parent.mkdir()
    model.write_bytes(b"model")

    report = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=manifest,
        source_catalog=catalog,
        min_positive_candidates=2,
        min_negative_candidates=3,
        min_train_images=2,
        min_valid_images=1,
    )

    assert report.passed is False
    assert any(check.name == "source_catalog" and not check.ok for check in report.checks)


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
    include_trace: bool = True,
) -> Path:
    manifest = tmp_path / "datasets" / "baseline" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    lines = []
    for index in range(positives):
        payload = {
            "profile": "positives",
            "license_reviewed": license_reviewed,
            "license_status": "cc-by" if license_reviewed else "unknown",
        }
        if include_trace:
            payload.update(
                {
                    "path": f"p{index}.jpg",
                    "url": f"https://example.test/p{index}.jpg",
                    "source": "web-search-candidates",
                }
            )
        lines.append(json.dumps(payload))
    for index in range(negatives):
        payload = {
            "profile": "negatives",
            "license_reviewed": license_reviewed,
            "license_status": "open-images" if license_reviewed else "unknown",
        }
        if include_trace:
            payload.update(
                {
                    "path": f"n{index}.jpg",
                    "image_id": f"img-{index}",
                    "source": "open-images",
                }
            )
        lines.append(json.dumps(payload))
    manifest.write_text("\n".join(lines) + "\n")
    return manifest


def _write_dataset(
    tmp_path: Path,
    *,
    train: int,
    valid: int,
    names: str,
    write_labels: bool = True,
    train_positive_labels: int | None = None,
    valid_positive_labels: int | None = None,
) -> Path:
    dataset = tmp_path / "datasets" / "control_vehicle_v1"
    train_dir = dataset / "train" / "images"
    valid_dir = dataset / "valid" / "images"
    train_label_dir = dataset / "train" / "labels"
    valid_label_dir = dataset / "valid" / "labels"
    train_dir.mkdir(parents=True)
    valid_dir.mkdir(parents=True)
    if write_labels:
        train_label_dir.mkdir(parents=True)
        valid_label_dir.mkdir(parents=True)
    (dataset / "data.yaml").write_text(names + "\n")
    train_positive_limit = train if train_positive_labels is None else train_positive_labels
    valid_positive_limit = valid if valid_positive_labels is None else valid_positive_labels
    for index in range(train):
        (train_dir / f"train-{index}.jpg").write_bytes(b"image")
        if write_labels and index < train_positive_limit:
            (train_label_dir / f"train-{index}.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    for index in range(valid):
        (valid_dir / f"valid-{index}.jpg").write_bytes(b"image")
        if write_labels and index < valid_positive_limit:
            (valid_label_dir / f"valid-{index}.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    return dataset
