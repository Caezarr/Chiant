from __future__ import annotations

import io
import os
import subprocess
import sys
import threading

import cv2
import numpy as np
import pytest

from boring.camera_sources import (
    CameraSettings,
    Picamera2Capture,
    RotatedCapture,
    RpicamCapture,
    make_capture,
    rpicam_command,
    split_jpeg_frames,
)
from boring.capture import probe_camera


def _jpeg(value: int, width: int = 64, height: int = 48) -> bytes:
    ok, encoded = cv2.imencode(".jpg", np.full((height, width, 3), value, dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def test_settings_from_env_defaults(monkeypatch):
    for name in (
        "CAMERA_BACKEND",
        "CAMERA_ROTATION",
        "CAMERA_WIDTH",
        "CAMERA_HEIGHT",
        "CAMERA_FRAMERATE",
        "CAMERA_LENS_POSITION",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = CameraSettings.from_env()

    assert settings == CameraSettings()
    assert settings.backend == "opencv"
    assert settings.lens_position == 0.0
    assert settings.validation_failures() == []


def test_settings_from_env_csi_box(monkeypatch):
    monkeypatch.setenv("CAMERA_BACKEND", "RPICAM")
    monkeypatch.setenv("CAMERA_ROTATION", "180")
    monkeypatch.setenv("CAMERA_WIDTH", "1536")
    monkeypatch.setenv("CAMERA_HEIGHT", "864")
    monkeypatch.setenv("CAMERA_FRAMERATE", "8")
    monkeypatch.setenv("CAMERA_LENS_POSITION", "auto")

    settings = CameraSettings.from_env()

    assert settings.backend == "rpicam"
    assert settings.rotation == 180
    assert (settings.width, settings.height) == (1536, 864)
    assert settings.framerate == 8
    assert settings.lens_position is None


def test_settings_validation_failures():
    settings = CameraSettings(backend="gstreamer", rotation=90, width=0, framerate=0)

    assert settings.validation_failures() == [
        "CAMERA_BACKEND=gstreamer",
        "CAMERA_ROTATION=90",
        "CAMERA_RESOLUTION=0x720",
        "CAMERA_FRAMERATE=0",
    ]


def test_make_capture_rejects_invalid_settings():
    with pytest.raises(ValueError, match="CAMERA_BACKEND=gstreamer"):
        make_capture(0, CameraSettings(backend="gstreamer"))


def test_split_jpeg_frames_handles_partial_chunks():
    first, second = _jpeg(10), _jpeg(200)
    stream = first + second

    frames, rest = split_jpeg_frames(stream[: len(first) + 5])
    assert frames == [first]
    assert rest == second[:5]

    frames, rest = split_jpeg_frames(rest + stream[len(first) + 5 :])
    assert frames == [second]
    assert rest == b""


def test_split_jpeg_frames_keeps_split_marker():
    frames, rest = split_jpeg_frames(b"garbage\xff")

    assert frames == []
    assert rest == b"\xff"


def test_rpicam_command_fixed_focus_and_autofocus():
    fixed = rpicam_command(1, CameraSettings(backend="rpicam", width=640, height=480))
    auto = rpicam_command(0, CameraSettings(backend="rpicam", lens_position=None))

    assert fixed[:3] == ["rpicam-vid", "--camera", "1"]
    assert fixed[fixed.index("--codec") + 1] == "mjpeg"
    assert fixed[fixed.index("--width") + 1] == "640"
    assert fixed[fixed.index("--output") + 1] == "-"
    assert fixed[fixed.index("--autofocus-mode") + 1] == "manual"
    assert fixed[fixed.index("--lens-position") + 1] == "0"
    assert auto[auto.index("--autofocus-mode") + 1] == "continuous"
    assert "--lens-position" not in auto


def test_rpicam_capture_returns_latest_decoded_frame():
    process = _FakeProcess(_jpeg(10) + _jpeg(200))
    capture = RpicamCapture(
        0,
        CameraSettings(backend="rpicam", read_timeout_seconds=2),
        popen=lambda *args, **kwargs: process,
    )

    ok, frame = capture.read()
    capture.release()

    assert ok is True
    assert frame.shape == (48, 64, 3)
    assert process.terminated is True


def test_rpicam_capture_fails_when_stream_ends():
    capture = RpicamCapture(
        0,
        CameraSettings(backend="rpicam", read_timeout_seconds=1),
        popen=lambda *args, **kwargs: _FakeProcess(b""),
    )

    ok, frame = capture.read()

    assert ok is False
    assert frame is None
    assert capture.isOpened() is False


def test_rpicam_capture_missing_binary_is_not_opened():
    def missing(*args, **kwargs):
        raise FileNotFoundError("rpicam-vid")

    capture = RpicamCapture(0, CameraSettings(backend="rpicam"), popen=missing)

    assert capture.isOpened() is False
    assert capture.read() == (False, None)
    capture.release()


def test_probe_camera_with_rpicam_backend():
    settings = CameraSettings(backend="rpicam", read_timeout_seconds=2)
    result = probe_camera(
        capture_factory=lambda index: RpicamCapture(
            index, settings, popen=lambda *args, **kwargs: _LiveProcess(_jpeg(90, 640, 480))
        )
    )

    assert result.ok is True
    assert (result.width, result.height) == (640, 480)


def test_probe_camera_reports_factory_error():
    def broken(_index):
        raise ValueError("configuration camera invalide: CAMERA_BACKEND=x")

    result = probe_camera(capture_factory=broken)

    assert result.ok is False
    assert "CAMERA_BACKEND=x" in result.error


def test_picamera2_capture_configures_fixed_focus():
    created: list[_FakePicamera2] = []

    def factory():
        def build(index):
            camera = _FakePicamera2(index)
            created.append(camera)
            return camera

        return build

    capture = Picamera2Capture(
        0, CameraSettings(backend="picamera2", width=640, height=480), picamera2_factory=factory
    )
    ok, frame = capture.read()
    capture.release()

    camera = created[0]
    assert capture.isOpened() is False
    assert ok is True
    assert frame.shape == (480, 640, 3)
    assert camera.configuration["main"] == {"size": (640, 480), "format": "RGB888"}
    assert camera.controls == {"AfMode": 0, "LensPosition": 0.0}
    assert camera.started and camera.stopped and camera.closed


def test_picamera2_capture_missing_library_is_not_opened():
    def missing():
        raise ImportError("No module named 'picamera2'")

    capture = Picamera2Capture(0, CameraSettings(backend="picamera2"), picamera2_factory=missing)

    assert capture.isOpened() is False
    assert "picamera2" in capture.error
    assert capture.read() == (False, None)


def test_rotated_capture_flips_frame():
    frame = np.zeros((2, 2, 3), dtype=np.uint8)
    frame[0, 0] = 255

    ok, rotated = RotatedCapture(_StaticCapture(frame)).read()

    assert ok is True
    assert rotated[1, 1].tolist() == [255, 255, 255]
    assert rotated[0, 0].tolist() == [0, 0, 0]


class _FakeProcess:
    def __init__(self, payload: bytes) -> None:
        self.stdout = io.BufferedReader(io.BytesIO(payload))
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout=None):
        if not self.terminated:
            raise subprocess.TimeoutExpired("rpicam-vid", timeout)
        return 0

    def kill(self) -> None:
        self.terminated = True


class _LiveStream:
    """Flux qui reste ouvert apres le premier envoi, comme une vraie camera."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.stopped = threading.Event()

    def read1(self, _size: int) -> bytes:
        payload, self.payload = self.payload, b""
        if payload:
            return payload
        self.stopped.wait(timeout=5)
        return b""

    def close(self) -> None:
        self.stopped.set()


class _LiveProcess(_FakeProcess):
    def __init__(self, payload: bytes) -> None:
        super().__init__(b"")
        self.stdout = _LiveStream(payload)

    def terminate(self) -> None:
        self.terminated = True
        self.stdout.stopped.set()


class _FakePicamera2:
    def __init__(self, index: int) -> None:
        self.index = index
        self.configuration = None
        self.controls = None
        self.started = self.stopped = self.closed = False

    def create_video_configuration(self, main, controls):
        return {"main": main, "controls": controls}

    def configure(self, configuration) -> None:
        self.configuration = configuration

    def start(self) -> None:
        self.started = True

    def set_controls(self, controls) -> None:
        self.controls = controls

    def capture_array(self, name):
        width, height = self.configuration["main"]["size"]
        return np.zeros((height, width, 3), dtype=np.uint8)

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class _StaticCapture:
    def __init__(self, frame) -> None:
        self.frame = frame

    def isOpened(self) -> bool:
        return True

    def read(self):
        return True, self.frame

    def release(self) -> None:
        pass


def test_rpicam_capture_end_to_end_with_real_subprocess(tmp_path, monkeypatch):
    """Vrai sous-processus, vrai tube : un faux rpicam-vid emet du MJPEG en continu."""
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(_jpeg(120, 320, 240))
    args_path = tmp_path / "args.txt"
    fake = tmp_path / "rpicam-vid"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        f"open({str(args_path)!r}, 'w').write(' '.join(sys.argv[1:]))\n"
        f"data = open({str(frame_path)!r}, 'rb').read()\n"
        "while True:\n"
        "    sys.stdout.buffer.write(data)\n"
        "    sys.stdout.buffer.flush()\n"
        "    time.sleep(0.02)\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    settings = CameraSettings(
        backend="rpicam", rotation=180, width=320, height=240, read_timeout_seconds=10
    )

    capture = make_capture(0, settings)
    try:
        assert capture.isOpened() is True
        shapes = [capture.read()[1].shape for _ in range(3)]
    finally:
        capture.release()

    assert shapes == [(240, 320, 3)] * 3
    assert "--codec mjpeg" in args_path.read_text()
    assert "--lens-position 0" in args_path.read_text()
    assert capture.isOpened() is False
