"""Tests du StreamTracker anti-faux-positif."""

from __future__ import annotations

from boring.detect import StreamTracker


def test_tracker_requires_consecutive_detections():
    t = StreamTracker(required_consecutive=3, window_seconds=10.0)
    assert t.update(True, 0.0) is False
    assert t.update(True, 0.1) is False
    assert t.update(True, 0.2) is True  # 3e frame consécutive


def test_tracker_resets_on_miss():
    t = StreamTracker(required_consecutive=3, window_seconds=10.0)
    t.update(True, 0.0)
    t.update(True, 0.1)
    t.update(False, 0.2)  # miss : reset
    assert t.update(True, 0.3) is False
    assert t.update(True, 0.4) is False
    assert t.update(True, 0.5) is True


def test_tracker_evicts_old_detections():
    """Les détections en dehors de la fenêtre temporelle sont oubliées."""
    t = StreamTracker(required_consecutive=3, window_seconds=1.0)
    t.update(True, 0.0)
    t.update(True, 0.5)
    # 2.0s plus tard, les deux précédentes sont hors fenêtre
    assert t.update(True, 2.0) is False


def test_tracker_with_required_one():
    """Trigger immédiat si required_consecutive=1."""
    t = StreamTracker(required_consecutive=1, window_seconds=10.0)
    assert t.update(True, 0.0) is True


def test_tracker_no_trigger_without_detection():
    t = StreamTracker(required_consecutive=3, window_seconds=10.0)
    for i in range(10):
        assert t.update(False, float(i)) is False
