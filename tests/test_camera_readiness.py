from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boring.camera_readiness import run_camera_check, write_report
from boring.capture import CameraProbeResult


def test_camera_check_passes_for_minimum_resolution():
    report = run_camera_check(
        probe=lambda _: CameraProbeResult(True, 0, width=640, height=480),
        now=_now(),
    )

    assert report.passed is True
    assert report.width == 640
    assert report.height == 480
    assert report.failures == []


def test_camera_check_fails_when_camera_unavailable():
    report = run_camera_check(
        probe=lambda _: CameraProbeResult(False, 0, error="camera not opened"),
    )

    assert report.passed is False
    assert "camera not opened" in report.failures
    assert "resolution=missing" in report.failures


def test_camera_check_fails_when_resolution_is_too_low():
    report = run_camera_check(
        min_width=640,
        min_height=480,
        probe=lambda _: CameraProbeResult(True, 0, width=320, height=240),
    )

    assert report.passed is False
    assert "width=320/640" in report.failures
    assert "height=240/480" in report.failures


def test_write_camera_report_includes_passed(tmp_path: Path):
    report = run_camera_check(
        probe=lambda _: CameraProbeResult(True, 0, width=1280, height=720),
        now=_now(),
    )
    output = tmp_path / "reports" / "camera-check.json"

    write_report(report, output)

    assert '"passed": true' in output.read_text()


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
