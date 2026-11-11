"""Sources camera du boitier : webcam OpenCV, camera CSI via rpicam ou picamera2.

Sur Raspberry Pi 5, une camera CSI (Camera Module 3) passe par libcamera et
n'est pas visible par ``cv2.VideoCapture(index)``. Deux backends la rendent
utilisable derriere la meme interface que ``cv2.VideoCapture`` :

- ``rpicam`` : lance ``rpicam-vid`` en sous-processus et lit son flux MJPEG.
  Aucune dependance Python, fonctionne quelle que soit la version de Python.
- ``picamera2`` : utilise la bibliotheque picamera2. Elle depend des bindings
  libcamera du Python systeme, donc d'un venv ``--system-site-packages`` sur la
  meme version de Python que Raspberry Pi OS.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import cv2
import numpy as np

CAMERA_BACKENDS = ("opencv", "rpicam", "picamera2")
CAMERA_ROTATIONS = (0, 180)

_JPEG_START = b"\xff\xd8"
_JPEG_END = b"\xff\xd9"
_READ_CHUNK_BYTES = 65536
_MAX_BUFFER_BYTES = 16 * 1024 * 1024


class FrameCapture(Protocol):
    """Sous-ensemble de ``cv2.VideoCapture`` utilise par le runtime."""

    def isOpened(self) -> bool: ...

    def read(self) -> tuple[bool, Any]: ...

    def release(self) -> None: ...


@dataclass(frozen=True)
class CameraSettings:
    backend: str = "opencv"
    rotation: int = 0
    width: int = 1280
    height: int = 720
    framerate: float = 10.0
    lens_position: float | None = 0.0
    read_timeout_seconds: float = 5.0

    def validation_failures(self) -> list[str]:
        failures: list[str] = []
        if self.backend not in CAMERA_BACKENDS:
            failures.append(f"CAMERA_BACKEND={self.backend}")
        if self.rotation not in CAMERA_ROTATIONS:
            failures.append(f"CAMERA_ROTATION={self.rotation}")
        if self.width <= 0 or self.height <= 0:
            failures.append(f"CAMERA_RESOLUTION={self.width}x{self.height}")
        if self.framerate <= 0:
            failures.append(f"CAMERA_FRAMERATE={self.framerate}")
        if self.lens_position is not None and self.lens_position < 0:
            failures.append(f"CAMERA_LENS_POSITION={self.lens_position}")
        return failures

    @classmethod
    def from_env(cls) -> CameraSettings:
        lens = os.getenv("CAMERA_LENS_POSITION", "0.0").strip().lower()
        return cls(
            backend=os.getenv("CAMERA_BACKEND", "opencv").strip().lower() or "opencv",
            rotation=int(os.getenv("CAMERA_ROTATION", "0")),
            width=int(os.getenv("CAMERA_WIDTH", "1280")),
            height=int(os.getenv("CAMERA_HEIGHT", "720")),
            framerate=float(os.getenv("CAMERA_FRAMERATE", "10")),
            # "auto" ou vide = autofocus continu ; un nombre = mise au point fixe
            # en dioptries (0.0 = infini, adapte a une camera derriere un pare-brise).
            lens_position=None if lens in {"", "auto"} else float(lens),
        )


def split_jpeg_frames(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Extrait les JPEG complets d'un flux MJPEG, retourne (frames, reste)."""
    frames: list[bytes] = []
    while True:
        start = buffer.find(_JPEG_START)
        if start < 0:
            # garde un eventuel 0xFF final, debut possible du prochain marqueur
            return frames, buffer[-1:] if buffer.endswith(b"\xff") else b""
        end = buffer.find(_JPEG_END, start + 2)
        if end < 0:
            return frames, buffer[start:]
        frames.append(buffer[start : end + 2])
        buffer = buffer[end + 2 :]


def rpicam_command(device_index: int, settings: CameraSettings) -> list[str]:
    command = [
        "rpicam-vid",
        "--camera",
        str(device_index),
        "--timeout",
        "0",
        "--nopreview",
        "--codec",
        "mjpeg",
        "--width",
        str(settings.width),
        "--height",
        str(settings.height),
        "--framerate",
        f"{settings.framerate:g}",
        "--flush",
        "--output",
        "-",
    ]
    if settings.lens_position is None:
        command += ["--autofocus-mode", "continuous"]
    else:
        command += [
            "--autofocus-mode",
            "manual",
            "--lens-position",
            f"{settings.lens_position:g}",
        ]
    return command


class RpicamCapture:
    """Camera CSI via ``rpicam-vid``. Un thread ne garde que la derniere image.

    La detection lit moins vite que la camera ne produit : sans ce thread, les
    images s'accumuleraient dans le tube et le runtime analyserait le passe.
    """

    def __init__(
        self,
        device_index: int,
        settings: CameraSettings,
        popen: Callable[..., Any] = subprocess.Popen,
    ) -> None:
        self._timeout = settings.read_timeout_seconds
        self._condition = threading.Condition()
        self._latest: bytes | None = None
        self._sequence = 0
        self._consumed = 0
        self._closed = False
        self._process: Any = None
        try:
            self._process = popen(
                rpicam_command(device_index, settings),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._closed = True
            return
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

    def _pump(self) -> None:
        buffer = b""
        stream = self._process.stdout
        try:
            while True:
                chunk = stream.read1(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                frames, buffer = split_jpeg_frames(buffer + chunk)
                if len(buffer) > _MAX_BUFFER_BYTES:
                    buffer = b""
                if frames:
                    with self._condition:
                        self._latest = frames[-1]
                        self._sequence += 1
                        self._condition.notify_all()
        finally:
            with self._condition:
                self._closed = True
                self._condition.notify_all()

    def isOpened(self) -> bool:
        return self._process is not None and not self._closed

    def read(self) -> tuple[bool, Any]:
        with self._condition:
            fresh = self._condition.wait_for(
                lambda: self._sequence != self._consumed or self._closed,
                timeout=self._timeout,
            )
            if not fresh or self._sequence == self._consumed:
                return False, None
            data = self._latest
            self._consumed = self._sequence
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return False, None
        return True, frame

    def release(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdout is not None:
            process.stdout.close()


def _import_picamera2() -> Any:
    from picamera2 import Picamera2  # type: ignore[import-not-found]

    return Picamera2


class Picamera2Capture:
    """Camera CSI via picamera2 (necessite les bindings libcamera systeme)."""

    _AF_MODE_MANUAL = 0
    _AF_MODE_CONTINUOUS = 2

    def __init__(
        self,
        device_index: int,
        settings: CameraSettings,
        picamera2_factory: Callable[[], Any] = _import_picamera2,
    ) -> None:
        self._camera: Any = None
        self.error: str | None = None
        try:
            camera = picamera2_factory()(device_index)
            # "RGB888" cote picamera2 = octets B,G,R en memoire, comme OpenCV.
            camera.configure(
                camera.create_video_configuration(
                    main={"size": (settings.width, settings.height), "format": "RGB888"},
                    controls={"FrameRate": settings.framerate},
                )
            )
            camera.start()
        except Exception as exc:  # ImportError, camera absente, libcamera
            self.error = str(exc)
            return
        self._camera = camera
        try:
            if settings.lens_position is None:
                camera.set_controls({"AfMode": self._AF_MODE_CONTINUOUS})
            else:
                camera.set_controls(
                    {"AfMode": self._AF_MODE_MANUAL, "LensPosition": settings.lens_position}
                )
        except Exception:
            # camera a focale fixe : pas de controle autofocus, on continue
            pass

    def isOpened(self) -> bool:
        return self._camera is not None

    def read(self) -> tuple[bool, Any]:
        if self._camera is None:
            return False, None
        try:
            frame = self._camera.capture_array("main")
        except Exception:
            return False, None
        return frame is not None, frame

    def release(self) -> None:
        camera, self._camera = self._camera, None
        if camera is None:
            return
        try:
            camera.stop()
        finally:
            camera.close()


class RotatedCapture:
    """Retourne l'image de 180 degres (camera montee connecteur vers le haut)."""

    def __init__(self, inner: FrameCapture) -> None:
        self._inner = inner

    def isOpened(self) -> bool:
        return self._inner.isOpened()

    def read(self) -> tuple[bool, Any]:
        ok, frame = self._inner.read()
        if not ok or frame is None:
            return ok, frame
        return True, cv2.rotate(frame, cv2.ROTATE_180)

    def release(self) -> None:
        self._inner.release()


def make_capture(device_index: int = 0, settings: CameraSettings | None = None) -> FrameCapture:
    """Ouvre la camera configuree par ``CAMERA_BACKEND``."""
    settings = settings or CameraSettings.from_env()
    failures = settings.validation_failures()
    if failures:
        raise ValueError(f"configuration camera invalide: {', '.join(failures)}")
    capture: FrameCapture
    if settings.backend == "rpicam":
        capture = RpicamCapture(device_index, settings)
    elif settings.backend == "picamera2":
        capture = Picamera2Capture(device_index, settings)
    else:
        capture = cv2.VideoCapture(device_index)
    if settings.rotation == 180:
        return RotatedCapture(capture)
    return capture
