from __future__ import annotations

from collections import namedtuple
from pathlib import Path

from boring.storage import DiskSpaceMonitor


Usage = namedtuple("Usage", ["total", "used", "free"])


def test_disk_space_monitor_reads_existing_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "boring.storage.shutil.disk_usage", lambda _: Usage(10_000_000, 1, 9_000_000)
    )

    status = DiskSpaceMonitor(tmp_path).check()

    assert status is not None
    assert status.path == str(tmp_path)
    assert status.free_mb == 9
    assert status.total_mb == 10


def test_disk_space_monitor_uses_parent_for_missing_file(tmp_path: Path, monkeypatch):
    calls = []

    def fake_disk_usage(path):
        calls.append(path)
        return Usage(10_000_000, 1, 8_000_000)

    monkeypatch.setattr("boring.storage.shutil.disk_usage", fake_disk_usage)

    status = DiskSpaceMonitor(tmp_path / "missing" / "events.jsonl").check()

    assert status is not None
    assert calls == [tmp_path / "missing"]


def test_disk_space_monitor_returns_none_on_os_error(tmp_path: Path, monkeypatch):
    def fake_disk_usage(_):
        raise OSError("nope")

    monkeypatch.setattr("boring.storage.shutil.disk_usage", fake_disk_usage)

    assert DiskSpaceMonitor(tmp_path).check() is None
