"""Audit local de readiness computer vision pour la Boring Parking Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from boring.vision_sources import load_source_catalog

APPROVED_LICENSE_STATUSES = {
    "approved",
    "owned",
    "public-domain",
    "cc0",
    "cc-by",
    "cc-by-sa",
    "open-images",
    "roboflow-allowed",
}


@dataclass(frozen=True)
class VisionCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class VisionReadinessReport:
    dataset_path: str
    model_path: str
    checks: list[VisionCheck]

    @property
    def passed(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def audit_vision_readiness(
    *,
    dataset_path: Path = Path("datasets/control_vehicle_v1"),
    model_path: Path = Path("models/best.pt"),
    baseline_manifest: Path = Path("datasets/baseline/manifest.jsonl"),
    source_catalog: Path = Path("data/vision_free_sources.json"),
    min_positive_candidates: int = 100,
    min_negative_candidates: int = 500,
    min_positive_sources: int = 2,
    min_negative_sources: int = 2,
    min_train_images: int = 300,
    min_valid_images: int = 50,
    min_train_positive_labels: int | None = None,
    min_valid_positive_labels: int | None = None,
    required_class: str = "control_vehicle",
    require_edge_export: bool = False,
    require_license_review: bool = True,
) -> VisionReadinessReport:
    checks = [
        _check_source_catalog(
            source_catalog,
            min_positive_sources=min_positive_sources,
            min_negative_sources=min_negative_sources,
        ),
        _check_baseline_manifest(
            baseline_manifest,
            min_positive_candidates=min_positive_candidates,
            min_negative_candidates=min_negative_candidates,
        ),
    ]
    if require_license_review:
        checks.append(_check_baseline_license_review(baseline_manifest))
    checks.append(_check_baseline_source_trace(baseline_manifest))
    checks.extend(
        [
            _check_yolo_dataset(
                dataset_path,
                min_train_images=min_train_images,
                min_valid_images=min_valid_images,
                min_train_positive_labels=(
                    min_train_positive_labels
                    if min_train_positive_labels is not None
                    else max(1, min_train_images // 5)
                ),
                min_valid_positive_labels=(
                    min_valid_positive_labels
                    if min_valid_positive_labels is not None
                    else max(1, min_valid_images // 5)
                ),
                required_class=required_class,
            ),
            _check_model(model_path),
        ]
    )
    if require_edge_export:
        checks.append(_check_edge_export(model_path))
    return VisionReadinessReport(str(dataset_path), str(model_path), checks)


def write_report(report: VisionReadinessReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _check_baseline_manifest(
    manifest: Path,
    *,
    min_positive_candidates: int,
    min_negative_candidates: int,
) -> VisionCheck:
    if not manifest.exists():
        return VisionCheck("baseline_manifest", False, f"missing {manifest}")
    positives = 0
    negatives = 0
    bad_lines = 0
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        profile = payload.get("profile")
        if profile == "positives":
            positives += 1
        elif profile == "negatives":
            negatives += 1
    ok = (
        positives >= min_positive_candidates
        and negatives >= min_negative_candidates
        and bad_lines == 0
    )
    return VisionCheck(
        "baseline_manifest",
        ok,
        (
            f"positives={positives}/{min_positive_candidates}, "
            f"negatives={negatives}/{min_negative_candidates}, bad_lines={bad_lines}"
        ),
    )


def _check_source_catalog(
    path: Path,
    *,
    min_positive_sources: int,
    min_negative_sources: int,
) -> VisionCheck:
    if not path.exists():
        return VisionCheck("source_catalog", False, f"missing {path}")
    try:
        catalog = load_source_catalog(path)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return VisionCheck("source_catalog", False, f"invalid {path}: {exc}")
    positives = catalog.count_trainable("positives")
    negatives = catalog.count_trainable("negatives")
    ok = positives >= min_positive_sources and negatives >= min_negative_sources
    return VisionCheck(
        "source_catalog",
        ok,
        (
            f"sources={len(catalog.sources)}, "
            f"positive_trainable={positives}/{min_positive_sources}, "
            f"negative_trainable={negatives}/{min_negative_sources}"
        ),
    )


def _check_baseline_license_review(manifest: Path) -> VisionCheck:
    if not manifest.exists():
        return VisionCheck("baseline_license_review", False, f"missing {manifest}")
    approved = 0
    unknown = 0
    bad_lines = 0
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        status = str(payload.get("license_status") or "").strip().lower()
        hint = str(payload.get("license_hint") or "").strip().lower()
        reviewed = bool(payload.get("license_reviewed"))
        if reviewed and (status in APPROVED_LICENSE_STATUSES or hint in APPROVED_LICENSE_STATUSES):
            approved += 1
        else:
            unknown += 1
    ok = approved > 0 and unknown == 0 and bad_lines == 0
    return VisionCheck(
        "baseline_license_review",
        ok,
        f"approved={approved}, unknown_or_unreviewed={unknown}, bad_lines={bad_lines}",
    )


def _check_baseline_source_trace(manifest: Path) -> VisionCheck:
    if not manifest.exists():
        return VisionCheck("baseline_source_trace", False, f"missing {manifest}")
    traced = 0
    missing_source = 0
    missing_locator = 0
    bad_lines = 0
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            bad_lines += 1
            continue
        source = str(payload.get("source") or "").strip()
        locator = _manifest_locator(payload)
        if not source:
            missing_source += 1
        if not locator:
            missing_locator += 1
        if source and locator:
            traced += 1
    ok = traced > 0 and missing_source == 0 and missing_locator == 0 and bad_lines == 0
    return VisionCheck(
        "baseline_source_trace",
        ok,
        (
            f"traced={traced}, missing_source={missing_source}, "
            f"missing_locator={missing_locator}, bad_lines={bad_lines}"
        ),
    )


def _manifest_locator(payload: dict) -> str:
    for key in ("url", "source_url", "source_page", "image_id", "path"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _check_yolo_dataset(
    dataset: Path,
    *,
    min_train_images: int,
    min_valid_images: int,
    min_train_positive_labels: int,
    min_valid_positive_labels: int,
    required_class: str,
) -> VisionCheck:
    data_yaml = dataset / "data.yaml"
    if not data_yaml.exists():
        return VisionCheck("yolo_dataset", False, f"missing {data_yaml}")
    train_images = _count_images(dataset / "train")
    valid_images = _count_images(dataset / "valid")
    class_map = _extract_yaml_class_map(data_yaml)
    class_index = _class_index(class_map, required_class)
    has_class = class_index is not None
    train_positive_labels = (
        _count_positive_labels(dataset / "train", class_index) if class_index is not None else 0
    )
    valid_positive_labels = (
        _count_positive_labels(dataset / "valid", class_index) if class_index is not None else 0
    )
    train_invalid_labels = _count_invalid_labels(dataset / "train", class_map)
    valid_invalid_labels = _count_invalid_labels(dataset / "valid", class_map)
    labels_ok = (
        train_positive_labels >= min_train_positive_labels
        and valid_positive_labels >= min_valid_positive_labels
    )
    label_format_ok = train_invalid_labels == 0 and valid_invalid_labels == 0
    ok = (
        train_images >= min_train_images
        and valid_images >= min_valid_images
        and has_class
        and labels_ok
        and label_format_ok
    )
    return VisionCheck(
        "yolo_dataset",
        ok,
        (
            f"train_images={train_images}/{min_train_images}, "
            f"valid_images={valid_images}/{min_valid_images}, "
            f"class={required_class if has_class else 'missing'}, "
            f"train_positive_labels={train_positive_labels}/{min_train_positive_labels}, "
            f"valid_positive_labels={valid_positive_labels}/{min_valid_positive_labels}, "
            f"invalid_labels={train_invalid_labels + valid_invalid_labels}"
        ),
    )


def _check_model(model: Path) -> VisionCheck:
    if not model.exists():
        return VisionCheck("model", False, f"missing {model}")
    if model.stat().st_size <= 0:
        return VisionCheck("model", False, f"empty {model}")
    return VisionCheck("model", True, f"present {model} ({model.stat().st_size} bytes)")


def _check_edge_export(model: Path) -> VisionCheck:
    candidates = [
        model.with_suffix(".onnx"),
        model.with_suffix(".tflite"),
        model.parent / "best.onnx",
        model.parent / "best.tflite",
    ]
    existing = [candidate for candidate in candidates if candidate.exists()]
    if not existing:
        return VisionCheck("edge_export", False, "missing best.onnx or best.tflite")
    return VisionCheck("edge_export", True, ", ".join(str(path) for path in existing))


def _count_images(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for path in root.glob("**/*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"})


def _extract_yaml_classes(data_yaml: Path) -> set[str]:
    return set(_extract_yaml_class_map(data_yaml).values())


def _extract_yaml_class_map(data_yaml: Path) -> dict[int, str]:
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
        if in_names_block:
            if ":" not in line:
                continue
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


def _class_index(class_map: dict[int, str], required_class: str) -> int | None:
    for index, name in class_map.items():
        if name == required_class:
            return index
    return None


def _count_positive_labels(split_root: Path, class_index: int) -> int:
    image_dir = split_root / "images"
    label_dir = split_root / "labels"
    if not image_dir.exists() or not label_dir.exists():
        return 0
    positives = 0
    for image_path in image_dir.glob("**/*"):
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        label_path = label_dir / f"{image_path.stem}.txt"
        if _label_has_class(label_path, class_index):
            positives += 1
    return positives


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


def _count_invalid_labels(split_root: Path, class_map: dict[int, str]) -> int:
    label_dir = split_root / "labels"
    if not label_dir.exists():
        return 0
    invalid = 0
    for label_path in label_dir.glob("**/*.txt"):
        for raw_line in label_path.read_text().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not _valid_yolo_label_line(line, class_map):
                invalid += 1
    return invalid


def _valid_yolo_label_line(line: str, class_map: dict[int, str]) -> bool:
    parts = line.split()
    if len(parts) != 5:
        return False
    try:
        raw_class_index = float(parts[0])
        if not raw_class_index.is_integer():
            return False
        class_index = int(raw_class_index)
        values = [float(value) for value in parts[1:]]
    except ValueError:
        return False
    return class_index in class_map and all(0.0 <= value <= 1.0 for value in values)
