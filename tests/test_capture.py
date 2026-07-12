from __future__ import annotations

import numpy as np

from boring.capture import probe_camera


def test_probe_camera_success():
    result = probe_camera(capture_factory=lambda _: _FakeCapture(opened=True, readable=True))

    assert result.ok is True
    assert result.width == 640
    assert result.height == 480


def test_probe_camera_not_opened():
    result = probe_camera(capture_factory=lambda _: _FakeCapture(opened=False, readable=False))

    assert result.ok is False
    assert result.error == "camera not opened"


def test_probe_camera_read_failure():
    result = probe_camera(capture_factory=lambda _: _FakeCapture(opened=True, readable=False))

    assert result.ok is False
    assert result.error == "camera read failed"


class _FakeCapture:
    def __init__(self, *, opened: bool, readable: bool) -> None:
        self.opened = opened
        self.readable = readable
        self.released = False

    def isOpened(self) -> bool:
        return self.opened

    def read(self):
        if not self.readable:
            return False, None
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True
