from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from boring.vision_eval import build_report, evaluate_yolo_dataset, write_report


class FakeDetector:
    def __init__(self, detections: list[bool]) -> None:
        self.detections = detections
        self.index = 0

    def detect_frame(self, frame, timestamp: float):
        detected = self.detections[self.index]
        self.index += 1
        return [object()] if detected else []


def test_vision_eval_report_passes_with_required_metrics(tmp_path: Path):
    report = build_report(
        model_path="models/best.pt",
        dataset_id="field-pi5-daylight-v1",
        recall=0.93,
        precision=0.98,
        false_positive_per_hour=0.5,
        evaluated_hours=3.0,
        dataset_path="datasets/control_vehicle_v1",
    )

    assert report.passed is True

    output = tmp_path / "reports" / "vision-eval.json"
    write_report(report, output)
    payload = json.loads(output.read_text())
    assert payload["passed"] is True
    assert payload["min_recall"] == 0.90
    assert payload["dataset_path"] == "datasets/control_vehicle_v1"


def test_vision_eval_report_fails_when_false_positive_rate_is_high():
    report = build_report(
        model_path="models/best.pt",
        dataset_id="field-pi5-daylight-v1",
        recall=0.95,
        precision=0.90,
        false_positive_per_hour=2.0,
        evaluated_hours=3.0,
    )

    assert report.passed is False


def test_evaluate_yolo_dataset_computes_metrics_from_labels(tmp_path: Path):
    dataset = _write_yolo_eval_dataset(tmp_path)
    detector = FakeDetector([True, False, True, False])

    report = evaluate_yolo_dataset(
        detector=detector,
        dataset_path=dataset,
        model_path="models/best.pt",
        dataset_id="unit-valid",
        split="valid",
        frame_interval_seconds=900,
        min_recall=0.40,
        max_false_positive_per_hour=2.0,
    )

    assert report.frames_evaluated == 4
    assert report.true_positives == 1
    assert report.false_negatives == 1
    assert report.false_positives == 1
    assert report.recall == 0.5
    assert report.precision == 0.5
    assert report.false_positive_per_hour == 1.0
    assert report.evaluated_hours == 1.0
    assert report.dataset_path == str(dataset)
    assert report.passed is True


def test_evaluate_yolo_dataset_fails_when_false_positives_exceed_hourly_limit(tmp_path: Path):
    dataset = _write_yolo_eval_dataset(tmp_path)
    detector = FakeDetector([True, True, True, False])

    report = evaluate_yolo_dataset(
        detector=detector,
        dataset_path=dataset,
        model_path="models/best.pt",
        dataset_id="unit-valid",
        split="valid",
        frame_interval_seconds=900,
        min_recall=0.40,
        max_false_positive_per_hour=1.0,
    )

    assert report.false_positives == 2
    assert report.false_positive_per_hour == 2.0
    assert report.passed is False


def _write_yolo_eval_dataset(tmp_path: Path) -> Path:
    dataset = tmp_path / "dataset"
    image_dir = dataset / "valid" / "images"
    label_dir = dataset / "valid" / "labels"
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    (dataset / "data.yaml").write_text("names: ['control_vehicle']\n")
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    for name in ("positive-a", "positive-b", "negative-a", "negative-b"):
        cv2.imwrite(str(image_dir / f"{name}.jpg"), image)
    (label_dir / "positive-a.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    (label_dir / "positive-b.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    return dataset
