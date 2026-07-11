from __future__ import annotations

import json

from boring.events import EventLog


def test_event_log_writes_jsonl(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")

    log.write("network_offline", target="probe", error="down")

    row = json.loads((tmp_path / "events.jsonl").read_text())
    assert row["event"] == "network_offline"
    assert row["target"] == "probe"
    assert row["error"] == "down"
    assert row["ts"]


def test_event_log_rotates_when_size_limit_is_reached(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path, max_bytes=120, backups=2)

    log.write("first", payload="x" * 80)
    log.write("second", payload="y" * 80)

    assert path.exists()
    assert (tmp_path / "events.jsonl.1").exists()
    current = json.loads(path.read_text())
    previous = json.loads((tmp_path / "events.jsonl.1").read_text())
    assert current["event"] == "second"
    assert previous["event"] == "first"


def test_event_log_keeps_configured_number_of_backups(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path, max_bytes=120, backups=2)

    log.write("first", payload="x" * 80)
    log.write("second", payload="y" * 80)
    log.write("third", payload="z" * 80)
    log.write("fourth", payload="w" * 80)

    assert path.exists()
    assert (tmp_path / "events.jsonl.1").exists()
    assert (tmp_path / "events.jsonl.2").exists()
    assert not (tmp_path / "events.jsonl.3").exists()
    oldest_kept = json.loads((tmp_path / "events.jsonl.2").read_text())
    assert oldest_kept["event"] == "second"


def test_event_log_rotation_can_be_disabled(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path, max_bytes=1, backups=0)

    log.write("first")
    log.write("second")

    assert not (tmp_path / "events.jsonl.1").exists()
    assert len(path.read_text().splitlines()) == 2
