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
    required_class: str
    recall: float
    precision: float
    false_positive_per_hour: float
    evaluated_hours: float
    min_recall: float
    max_false_positive_per_hour: float
    passed: bool
    frames_evaluated: int = 0
    positive_frames_evaluated: int = 0
    negative_frames_evaluated: int = 0
    negative_evaluated_hours: float = 0.0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    invalid_images: int = 0
    invalid_labels: int = 0
    dataset_path: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_report(
    *,
    model_path: str,
    dataset_id: str,
    required_class: str = "control_vehicle",
    recall: float,
    precision: float,
    false_positive_per_hour: float,
    evaluated_hours: float,
    min_recall: float = 0.90,
    max_false_positive_per_hour: float = 1.0,
    frames_evaluated: int = 0,
    positive_frames_evaluated: int = 0,
    negative_frames_evaluated: int = 0,
    negative_evaluated_hours: float = 0.0,
    true_positives: int = 0,
    false_positives: int = 0,
    false_negatives: int = 0,
    invalid_images: int = 0,
    invalid_labels: int = 0,
    dataset_path: str = "",
) -> VisionEvalReport:
    passed = (
        recall >= min_recall
        and false_positive_per_hour <= max_false_positive_per_hour
        and evaluated_hours > 0
        and frames_evaluated > 0
        and positive_frames_evaluated > 0
        and negative_frames_evaluated > 0
        and negative_evaluated_hours > 0
        and true_positives > 0
        and invalid_images == 0
        and invalid_labels == 0
    )
    return VisionEvalReport(
        model_path=model_path,
        dataset_id=dataset_id,
        required_class=required_class,
        recall=recall,
        precision=precision,
        false_positive_per_hour=false_positive_per_hour,
        evaluated_hours=evaluated_hours,
        min_recall=min_recall,
        max_false_positive_per_hour=max_false_positive_per_hour,
        passed=passed,
        frames_evaluated=frames_evaluated,
        positive_frames_evaluated=positive_frames_evaluated,
        negative_frames_evaluated=negative_frames_evaluated,
        negative_evaluated_hours=negative_evaluated_hours,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        invalid_images=invalid_images,
        invalid_labels=invalid_labels,
        dataset_path=dataset_path,
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
    class_map = _extract_yaml_classes(dataset_path / "data.yaml")
    class_index = _required_class_index(class_map, required_class)
    image_dir = dataset_path / split / "images"
    label_dir = dataset_path / split / "labels"
    images = sorted(
        path for path in image_dir.glob("**/*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    invalid_images = 0
    invalid_labels = 0
    frames_evaluated = 0
    positive_frames_evaluated = 0
    negative_frames_evaluated = 0
    for index, image_path in enumerate(images):
        frame = cv2.imread(str(image_path))
        if frame is None:
            invalid_images += 1
            continue
        label_result = _read_label_file(
            label_dir / f"{image_path.stem}.txt",
            class_index,
            class_map,
        )
        invalid_labels += label_result.invalid_lines
        expected = label_result.has_required_class
        if expected:
            positive_frames_evaluated += 1
        else:
            negative_frames_evaluated += 1
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
    negative_evaluated_hours = negative_frames_evaluated * frame_interval_seconds / 3600
    false_positive_per_hour = (
        false_positives / negative_evaluated_hours if negative_evaluated_hours > 0 else float("inf")
    )
    return build_report(
        model_path=model_path,
        dataset_id=dataset_id,
        required_class=required_class,
        dataset_path=str(dataset_path),
        recall=recall,
        precision=precision,
        false_positive_per_hour=false_positive_per_hour,
        evaluated_hours=evaluated_hours,
        min_recall=min_recall,
        max_false_positive_per_hour=max_false_positive_per_hour,
        frames_evaluated=frames_evaluated,
        positive_frames_evaluated=positive_frames_evaluated,
        negative_frames_evaluated=negative_frames_evaluated,
        negative_evaluated_hours=negative_evaluated_hours,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        invalid_images=invalid_images,
        invalid_labels=invalid_labels,
    )


def write_report(report: VisionEvalReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _required_class_index(classes: dict[int, str], required_class: str) -> int:
    for index, name in classes.items():
        if name == required_class:
            return index
    raise ValueError(f"class {required_class!r} missing from data.yaml")


@dataclass(frozen=True)
class LabelFileResult:
    has_required_class: bool
    invalid_lines: int


def _read_label_file(
    label_path: Path,
    class_index: int,
    class_map: dict[int, str],
) -> LabelFileResult:
    if not label_path.exists():
        return LabelFileResult(False, 0)
    has_required_class = False
    invalid_lines = 0
    for raw_line in label_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed_class = _parse_yolo_label_class(line, class_map)
        if parsed_class is None:
            invalid_lines += 1
            continue
        if parsed_class == class_index:
            has_required_class = True
    return LabelFileResult(has_required_class, invalid_lines)


def _parse_yolo_label_class(line: str, class_map: dict[int, str]) -> int | None:
    parts = line.split()
    if len(parts) != 5:
        return None
    try:
        raw_class_index = float(parts[0])
        if not raw_class_index.is_integer():
            return None
        class_index = int(raw_class_index)
        values = [float(value) for value in parts[1:]]
    except ValueError:
        return None
    if class_index not in class_map or not all(0.0 <= value <= 1.0 for value in values):
        return None
    return class_index


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
