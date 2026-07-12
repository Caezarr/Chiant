"""Benchmark headless de la detection sur hardware cible."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class VisionBenchmarkReport:
    model_path: str
    device: str
    frames_processed: int
    detections_seen: int
    duration_seconds: float
    measured_fps: float
    min_fps: float
    passed: bool


def run_vision_benchmark(
    *,
    detector,
    frames: Iterable[tuple[float, object]],
    model_path: str,
    device: str,
    min_fps: float,
    max_frames: int,
    clock=time.perf_counter,
) -> VisionBenchmarkReport:
    started = clock()
    frames_processed = 0
    detections_seen = 0
    for timestamp, frame in frames:
        detections = detector.detect_frame(frame, timestamp)
        frames_processed += 1
        detections_seen += len(detections)
        if frames_processed >= max_frames:
            break
    ended = clock()
    duration = max(0.0, ended - started)
    measured_fps = frames_processed / duration if duration > 0 else 0.0
    return VisionBenchmarkReport(
        model_path=model_path,
        device=device,
        frames_processed=frames_processed,
        detections_seen=detections_seen,
        duration_seconds=duration,
        measured_fps=measured_fps,
        min_fps=min_fps,
        passed=frames_processed > 0 and measured_fps >= min_fps,
    )


def write_report(report: VisionBenchmarkReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2, sort_keys=True) + "\n")
