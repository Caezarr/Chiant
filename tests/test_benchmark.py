from __future__ import annotations

import json
from pathlib import Path

from boring.benchmark import run_vision_benchmark, write_report


def test_run_vision_benchmark_passes_when_fps_is_high_enough():
    clock = _FakeClock([0.0, 2.0])
    detector = _FakeDetector(detections_per_frame=1)

    report = run_vision_benchmark(
        detector=detector,
        frames=[(1.0, object()), (2.0, object()), (3.0, object()), (4.0, object())],
        model_path="models/best.pt",
        device="cpu",
        min_fps=2.0,
        max_frames=4,
        clock=clock,
    )

    assert report.passed is True
    assert report.frames_processed == 4
    assert report.detections_seen == 4
    assert report.measured_fps == 2.0
    assert report.target_labels == ("control_vehicle",)


def test_run_vision_benchmark_fails_without_frames():
    report = run_vision_benchmark(
        detector=_FakeDetector(),
        frames=[],
        model_path="models/best.pt",
        device="cpu",
        min_fps=1.0,
        max_frames=4,
        clock=_FakeClock([0.0, 1.0]),
    )

    assert report.passed is False
    assert report.frames_processed == 0


def test_run_vision_benchmark_fails_when_too_slow():
    report = run_vision_benchmark(
        detector=_FakeDetector(detections_per_frame=1),
        frames=[(1.0, object()), (2.0, object())],
        model_path="models/best.pt",
        device="cpu",
        min_fps=2.0,
        max_frames=2,
        clock=_FakeClock([0.0, 2.0]),
    )

    assert report.passed is False
    assert report.measured_fps == 1.0


def test_run_vision_benchmark_fails_without_positive_detections():
    report = run_vision_benchmark(
        detector=_FakeDetector(detections_per_frame=0),
        frames=[(1.0, object()), (2.0, object())],
        model_path="models/best.pt",
        device="cpu",
        min_fps=1.0,
        max_frames=2,
        clock=_FakeClock([0.0, 1.0]),
    )

    assert report.passed is False
    assert report.frames_processed == 2
    assert report.detections_seen == 0
    assert report.measured_fps == 2.0


def test_write_report(tmp_path: Path):
    report = run_vision_benchmark(
        detector=_FakeDetector(detections_per_frame=1),
        frames=[(1.0, object())],
        model_path="models/best.pt",
        device="cpu",
        min_fps=1.0,
        max_frames=1,
        clock=_FakeClock([0.0, 1.0]),
    )
    output = tmp_path / "reports" / "vision-benchmark.json"

    write_report(report, output)

    payload = json.loads(output.read_text())
    assert payload["frames_processed"] == 1
    assert payload["target_labels"] == ["control_vehicle"]


class _FakeDetector:
    def __init__(self, detections_per_frame: int = 0) -> None:
        self.detections_per_frame = detections_per_frame

    def detect_frame(self, frame, timestamp: float) -> list[object]:
        return [object()] * self.detections_per_frame


class _FakeClock:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def __call__(self) -> float:
        return self.values.pop(0)
