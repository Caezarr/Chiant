"""Audit local de readiness computer vision pour la Boring Parking Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

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
    min_positive_candidates: int = 100,
    min_negative_candidates: int = 500,
    min_train_images: int = 300,
    min_valid_images: int = 50,
    required_class: str = "control_vehicle",
    require_edge_export: bool = False,
    require_license_review: bool = True,
) -> VisionReadinessReport:
    checks = [
        _check_baseline_manifest(
            baseline_manifest,
            min_positive_candidates=min_positive_candidates,
            min_negative_candidates=min_negative_candidates,
        ),
    ]
    if require_license_review:
        checks.append(_check_baseline_license_review(baseline_manifest))
    checks.extend(
        [
            _check_yolo_dataset(
                dataset_path,
                min_train_images=min_train_images,
                min_valid_images=min_valid_images,
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


def _check_yolo_dataset(
    dataset: Path,
    *,
    min_train_images: int,
    min_valid_images: int,
    required_class: str,
) -> VisionCheck:
    data_yaml = dataset / "data.yaml"
    if not data_yaml.exists():
        return VisionCheck("yolo_dataset", False, f"missing {data_yaml}")
    train_images = _count_images(dataset / "train")
    valid_images = _count_images(dataset / "valid")
    classes = _extract_yaml_classes(data_yaml)
    has_class = required_class in classes
    ok = train_images >= min_train_images and valid_images >= min_valid_images and has_class
    return VisionCheck(
        "yolo_dataset",
        ok,
        (
            f"train_images={train_images}/{min_train_images}, "
            f"valid_images={valid_images}/{min_valid_images}, "
            f"class={required_class if has_class else 'missing'}"
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
    text = data_yaml.read_text()
    classes: set[str] = set()
    in_names_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("names:"):
            value = line.split(":", 1)[1].strip()
            if value.startswith("[") and value.endswith("]"):
                for item in value.strip("[]").split(","):
                    classes.add(item.strip().strip("'\""))
                in_names_block = False
            else:
                in_names_block = True
            continue
        if in_names_block:
            if ":" not in line:
                continue
            _, value = line.split(":", 1)
            classes.add(value.strip().strip("'\""))
    return {name for name in classes if name}
