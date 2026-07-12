"""Runtime camera readiness check for a Boring Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from boring.capture import CameraProbeResult, probe_camera


@dataclass(frozen=True)
class CameraCheckReport:
    passed: bool
    device_index: int
    width: int | None
    height: int | None
    min_width: int
    min_height: int
    checked_at: str
    failures: list[str]
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_camera_check(
    *,
    device_index: int = 0,
    min_width: int = 640,
    min_height: int = 480,
    probe: Callable[[int], CameraProbeResult] = probe_camera,
    now: datetime | None = None,
) -> CameraCheckReport:
    result = probe(device_index)
    checked_at = (now or datetime.now(timezone.utc)).isoformat()
    failures = _camera_failures(result, min_width=min_width, min_height=min_height)
    return CameraCheckReport(
        passed=not failures,
        device_index=device_index,
        width=result.width,
        height=result.height,
        min_width=min_width,
        min_height=min_height,
        checked_at=checked_at,
        failures=failures,
        error=result.error,
    )


def write_report(report: CameraCheckReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _camera_failures(
    result: CameraProbeResult,
    *,
    min_width: int,
    min_height: int,
) -> list[str]:
    failures = []
    if not result.ok:
        failures.append(result.error or "camera_unavailable")
    if result.width is None or result.height is None:
        failures.append("resolution=missing")
    else:
        if result.width < min_width:
            failures.append(f"width={result.width}/{min_width}")
        if result.height < min_height:
            failures.append(f"height={result.height}/{min_height}")
    return failures
