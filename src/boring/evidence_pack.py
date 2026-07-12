"""Pack de preuves terrain pour une Boring Box."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class EvidenceItem:
    name: str
    path: str
    present: bool
    valid_json: bool
    passed: bool | None
    size_bytes: int | None
    sha256: str | None
    detail: str


@dataclass(frozen=True)
class EvidencePack:
    generated_at: str
    items: list[EvidenceItem]

    @property
    def passed(self) -> bool:
        return all(evidence_item_ok(item) for item in self.items)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


def build_evidence_pack(paths: dict[str, Path]) -> EvidencePack:
    return EvidencePack(
        generated_at=datetime.now(timezone.utc).isoformat(),
        items=[_read_item(name, path) for name, path in paths.items()],
    )


def write_pack(pack: EvidencePack, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pack.to_dict(), indent=2, sort_keys=True) + "\n")


def default_evidence_paths() -> dict[str, Path]:
    return {
        "box_ready": Path("reports/box-readiness.json"),
        "hardware_profile": Path("deploy/pi/hardware-profile.json"),
        "systemd_runtime": Path("reports/systemd-check.json"),
        "position_runtime": Path("reports/position-check.json"),
        "camera_runtime": Path("reports/camera-check.json"),
        "network_runtime": Path("reports/network-check.json"),
        "vision_eval": Path("reports/vision-eval.json"),
        "vision_benchmark": Path("reports/vision-benchmark.json"),
        "autopay_smoke": Path("reports/autopay-smoke.json"),
        "notification_test": Path("reports/notification-test.json"),
        "burn_in": Path("burn-in/report.json"),
    }


def evidence_item_ok(item: EvidenceItem) -> bool:
    if not item.present or not item.valid_json:
        return False
    if item.name == "hardware_profile":
        return item.passed is not False
    return item.passed is True


def _read_item(name: str, path: Path) -> EvidenceItem:
    if not path.exists():
        return EvidenceItem(name, str(path), False, False, None, None, None, "missing")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return EvidenceItem(
            name,
            str(path),
            True,
            False,
            None,
            len(raw),
            hashlib.sha256(raw).hexdigest(),
            "invalid json",
        )
    passed = payload.get("passed") if isinstance(payload, dict) else None
    return EvidenceItem(
        name=name,
        path=str(path),
        present=True,
        valid_json=True,
        passed=passed if isinstance(passed, bool) else None,
        size_bytes=len(raw),
        sha256=hashlib.sha256(raw).hexdigest(),
        detail=_detail(payload),
    )


def _detail(payload) -> str:
    if not isinstance(payload, dict):
        return "json is not an object"
    if "passed" in payload:
        return f"passed={payload.get('passed')}"
    return "json present"
