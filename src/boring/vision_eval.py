"""Rapport d'evaluation terrain du modele de detection."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2

from boring.detect import Detector


@dataclass(frozen=True)
class VisionEvalReport:
    model_path: str
    dataset_id: str
    recall: float
    precision: float
    false_positive_per_hour: float
    evaluated_hours: float
    min_recall: float
    max_false_positive_per_hour: float
    passed: bool
    frames_evaluated: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    invalid_images: int = 0
    generated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_report(
    *,
    model_path: str,
    dataset_id: str,
    recall: float,
    precision: float,
    false_positive_per_hour: float,
    evaluated_hours: float,
    min_recall: float = 0.90,
    max_false_positive_per_hour: float = 1.0,
    frames_evaluated: int = 0,
    true_positives: int = 0,
    false_positives: int = 0,
    false_negatives: int = 0,
    invalid_images: int = 0,
) -> VisionEvalReport:
    passed = (
        recall >= min_recall
        and false_positive_per_hour <= max_false_positive_per_hour
        and evaluated_hours > 0
        and frames_evaluated >= 0
        and invalid_images == 0
    )
    return VisionEvalReport(
        model_path=model_path,
        dataset_id=dataset_id,
        recall=recall,
        precision=precision,
        false_positive_per_hour=false_positive_per_hour,
        evaluated_hours=evaluated_hours,
        min_recall=min_recall,
        max_false_positive_per_hour=max_false_positive_per_hour,
        passed=passed,
        frames_evaluated=frames_evaluated,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        invalid_images=invalid_images,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def evaluate_yolo_dataset(
    *,
    detector: Detector,
    dataset_path: Path,
    model_path: str,
    dataset_id: str,
    split: str = "valid",
    required_class: str = "control_vehicle",
    frame_interval_seconds: float = 1.0,
    min_recall: float = 0.90,
    max_false_positive_per_hour: float = 1.0,
) -> VisionEvalReport:
    class_index = _required_class_index(dataset_path / "data.yaml", required_class)
    image_dir = dataset_path / split / "images"
    label_dir = dataset_path / split / "labels"
    images = sorted(
        path for path in image_dir.glob("**/*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    invalid_images = 0
    frames_evaluated = 0
    for index, image_path in enumerate(images):
        frame = cv2.imread(str(image_path))
        if frame is None:
            invalid_images += 1
            continue
        expected = _label_has_class(label_dir / f"{image_path.stem}.txt", class_index)
        detected = bool(
            detector.detect_frame(frame, timestamp=float(index) * frame_interval_seconds)
        )
        frames_evaluated += 1
        if expected and detected:
            true_positives += 1
        elif expected and not detected:
            false_negatives += 1
        elif not expected and detected:
            false_positives += 1

    recall_denominator = true_positives + false_negatives
    precision_denominator = true_positives + false_positives
    recall = true_positives / recall_denominator if recall_denominator else 0.0
    precision = true_positives / precision_denominator if precision_denominator else 0.0
    evaluated_hours = frames_evaluated * frame_interval_seconds / 3600
    false_positive_per_hour = (
        false_positives / evaluated_hours if evaluated_hours > 0 else float("inf")
    )
    return build_report(
        model_path=model_path,
        dataset_id=dataset_id,
        recall=recall,
        precision=precision,
        false_positive_per_hour=false_positive_per_hour,
        evaluated_hours=evaluated_hours,
        min_recall=min_recall,
        max_false_positive_per_hour=max_false_positive_per_hour,
        frames_evaluated=frames_evaluated,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        invalid_images=invalid_images,
    )


def write_report(report: VisionEvalReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _required_class_index(data_yaml: Path, required_class: str) -> int:
    classes = _extract_yaml_classes(data_yaml)
    for index, name in classes.items():
        if name == required_class:
            return index
    raise ValueError(f"class {required_class!r} missing from {data_yaml}")


def _label_has_class(label_path: Path, class_index: int) -> bool:
    if not label_path.exists():
        return False
    for raw_line in label_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        first = line.split(maxsplit=1)[0]
        try:
            if int(float(first)) == class_index:
                return True
        except ValueError:
            continue
    return False


def _extract_yaml_classes(data_yaml: Path) -> dict[int, str]:
    text = data_yaml.read_text()
    classes: dict[int, str] = {}
    in_names_block = False
    next_index = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("names:"):
            value = line.split(":", 1)[1].strip()
            if value.startswith("[") and value.endswith("]"):
                for index, item in enumerate(value.strip("[]").split(",")):
                    name = item.strip().strip("'\"")
                    if name:
                        classes[index] = name
                in_names_block = False
            else:
                in_names_block = True
                next_index = 0
            continue
        if in_names_block and ":" in line:
            raw_key, raw_value = line.split(":", 1)
            value = raw_value.strip().strip("'\"")
            try:
                index = int(raw_key.strip())
            except ValueError:
                index = next_index
            if value:
                classes[index] = value
                next_index = max(next_index, index + 1)
    return classes
