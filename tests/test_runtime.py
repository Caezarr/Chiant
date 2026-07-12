from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from boring.capture import CameraProbeResult
from boring.config import BoxConfig
from boring.events import EventLog
from boring.network import NetworkStatus
from boring.position import StaticPositionProvider
from boring.power import BatteryStatus, ThermalStatus
from boring.runtime import (
    RuntimeState,
    _check_disk,
    _check_network,
    _check_power,
    _check_thermal,
    _current_inference_fps,
    _handle_trigger,
    _heartbeat,
    box_doctor,
)
from boring.state import BoxStateStore
from boring.storage import DiskStatus


def test_box_doctor_fails_for_unsafe_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "boring.runtime.probe_camera",
        lambda _: CameraProbeResult(False, 0, error="missing"),
    )
    config = BoxConfig(
        vehicle_plate="AA-000-AA",
        lat=None,
        lon=None,
        zones_path=tmp_path / "missing.geojson",
        state_path=tmp_path / "missing" / "state.json",
        event_log_path=tmp_path / "missing" / "events.jsonl",
        payment_dry_run=True,
        battery_capacity_wh=20,
    )

    assert box_doctor(config) == 1


def test_box_doctor_accepts_minimal_real_config(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "boring.runtime.probe_camera",
        lambda _: CameraProbeResult(True, 0, width=640, height=480),
    )
    zones = tmp_path / "zones.geojson"
    zones.write_text('{"type":"FeatureCollection","features":[]}')
    model = tmp_path / "best.pt"
    model.write_text("stub")
    config = BoxConfig(
        vehicle_plate="AB-123-CD",
        model_path=str(model),
        lat=50.6371,
        lon=3.0633,
        zones_path=zones,
        state_path=tmp_path / "state.json",
        event_log_path=tmp_path / "events.jsonl",
        payment_dry_run=False,
        max_session_amount_cents=500,
        max_daily_amount_cents=1500,
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        required_runtime_hours=10,
        vehicle_charge_watts=30,
        daily_drive_recharge_hours=1,
        notify_webhook_url="https://notify.example.test/boring",
        network_recovery_command="systemctl restart NetworkManager",
    )

    assert box_doctor(config) == 0


def test_box_doctor_fails_for_invalid_runtime_config(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "boring.runtime.probe_camera",
        lambda _: CameraProbeResult(True, 0, width=640, height=480),
    )
    zones = tmp_path / "zones.geojson"
    zones.write_text('{"type":"FeatureCollection","features":[]}')
    model = tmp_path / "best.pt"
    model.write_text("stub")
    config = BoxConfig(
        vehicle_plate="AB-123-CD",
        model_path=str(model),
        lat=50.6371,
        lon=3.0633,
        zones_path=zones,
        state_path=tmp_path / "state.json",
        event_log_path=tmp_path / "events.jsonl",
        payment_dry_run=False,
        battery_capacity_wh=100,
        estimated_draw_watts=8,
        required_runtime_hours=10,
        vehicle_charge_watts=30,
        notify_webhook_url="https://notify.example.test/boring",
        network_recovery_command="systemctl restart NetworkManager",
        battery_low_percent=25,
        battery_critical_percent=30,
    )

    assert box_doctor(config) == 1


def test_handle_trigger_skips_payment_when_offline(tmp_path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    event_log = EventLog(tmp_path / "events.jsonl")
    result = _handle_trigger(
        payment=object(),
        cooldown=object(),
        state_store=BoxStateStore(tmp_path / "state.json"),
        event_log=event_log,
        state=RuntimeState(network_online=False),
        config=BoxConfig(vehicle_plate="AB-123-CD"),
        position_provider=StaticPositionProvider(50.6371, 3.0633),
        zones=None,
        detection_count=2,
    )

    assert result is None
    assert calls[0][0] == "Boring Box — paiement bloque"
    assert "payment_skipped_offline" in (tmp_path / "events.jsonl").read_text()


def test_handle_trigger_skips_payment_without_position(tmp_path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    result = _handle_trigger(
        payment=object(),
        cooldown=object(),
        state_store=BoxStateStore(tmp_path / "state.json"),
        event_log=EventLog(tmp_path / "events.jsonl"),
        state=RuntimeState(network_online=True),
        config=BoxConfig(vehicle_plate="AB-123-CD"),
        position_provider=StaticPositionProvider(None, None),
        zones=None,
        detection_count=1,
    )

    assert result is None
    assert calls[0][0] == "Boring Box — paiement bloque"
    assert "payment_skipped_no_position" in (tmp_path / "events.jsonl").read_text()


def test_handle_trigger_skips_payment_when_battery_is_critical(tmp_path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    event_log = EventLog(tmp_path / "events.jsonl")
    result = _handle_trigger(
        payment=object(),
        cooldown=object(),
        state_store=BoxStateStore(tmp_path / "state.json"),
        event_log=event_log,
        state=RuntimeState(battery_critical_active=True, network_online=True),
        config=BoxConfig(vehicle_plate="AB-123-CD"),
        position_provider=StaticPositionProvider(50.6371, 3.0633),
        zones=None,
        detection_count=1,
    )

    assert result is None
    assert calls[0][0] == "Boring Box — paiement bloque"
    assert "Batterie critique" in calls[0][1]
    assert "payment_skipped_battery_critical" in (tmp_path / "events.jsonl").read_text()


def test_handle_trigger_skips_payment_when_state_file_is_corrupt(tmp_path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    state_path = tmp_path / "state.json"
    state_path.write_text("{not-json")
    event_log = EventLog(tmp_path / "events.jsonl")
    provider = object()

    result = _handle_trigger(
        payment=provider,
        cooldown=object(),
        state_store=BoxStateStore(state_path),
        event_log=event_log,
        state=RuntimeState(network_online=True),
        config=BoxConfig(vehicle_plate="AB-123-CD"),
        position_provider=StaticPositionProvider(50.6371, 3.0633),
        zones=None,
        detection_count=1,
    )

    assert result is None
    assert calls == [
        (
            "Boring Box — paiement bloque",
            "Etat local illisible: verifier /var/lib/boring/state.json avant autopaiement.",
            True,
        )
    ]
    assert "payment_skipped_state_corrupt" in (tmp_path / "events.jsonl").read_text()


def test_handle_trigger_logs_notification_failure_when_payment_is_blocked(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: False)
    event_log = EventLog(tmp_path / "events.jsonl")

    result = _handle_trigger(
        payment=object(),
        cooldown=object(),
        state_store=BoxStateStore(tmp_path / "state.json"),
        event_log=event_log,
        state=RuntimeState(network_online=False),
        config=BoxConfig(vehicle_plate="AB-123-CD"),
        position_provider=StaticPositionProvider(50.6371, 3.0633),
        zones=None,
        detection_count=2,
    )

    assert result is None
    events = (tmp_path / "events.jsonl").read_text()
    assert "payment_skipped_offline" in events
    assert "notification_failed" in events
    assert "network_offline" in events


def test_check_network_notifies_offline_then_recovered(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(network_check_seconds=1)
    state = RuntimeState(last_network_check=-10)
    network = _FakeNetwork(
        [
            NetworkStatus(False, "probe", "down"),
            NetworkStatus(True, "probe"),
        ]
    )

    event_log = EventLog(tmp_path / "events.jsonl")

    _check_network(0, network, state, config, event_log)
    assert state.network_offline_alert_sent is True
    _check_network(2, network, state, config, event_log)

    assert calls[0][0] == "Boring Box — reseau indisponible"
    assert calls[0][2] is True
    assert calls[1][0] == "Boring Box — reseau revenu"
    assert state.network_offline_alert_sent is False
    events = (tmp_path / "events.jsonl").read_text()
    assert "network_offline" in events
    assert "network_recovered" in events


def test_check_network_logs_notification_failure_when_offline(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: False)
    config = BoxConfig(network_check_seconds=1)
    state = RuntimeState(last_network_check=-10)
    network = _FakeNetwork([NetworkStatus(False, "probe", "down")])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_network(0, network, state, config, event_log)

    events = (tmp_path / "events.jsonl").read_text()
    assert "network_offline" in events
    assert "notification_failed" in events
    assert "probe" in events


def test_check_network_runs_recovery_command_when_offline(tmp_path: Path, monkeypatch):
    calls = []

    def fake_recovery(command: str, *, timeout_seconds: float):
        calls.append((command, timeout_seconds))
        return SimpleNamespace(
            command=command,
            ok=True,
            returncode=0,
            error=None,
            stderr="",
        )

    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: None)
    monkeypatch.setattr("boring.runtime.run_network_recovery", fake_recovery)
    config = BoxConfig(
        network_check_seconds=1,
        network_recovery_command="systemctl restart NetworkManager",
        network_recovery_cooldown_seconds=300,
        network_recovery_timeout_seconds=12,
    )
    state = RuntimeState(last_network_check=-10)
    network = _FakeNetwork(
        [
            NetworkStatus(False, "probe", "down"),
            NetworkStatus(False, "probe", "still down"),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_network(0, network, state, config, event_log)
    _check_network(2, network, state, config, event_log)

    assert calls == [("systemctl restart NetworkManager", 12)]
    assert "network_recovery_attempted" in (tmp_path / "events.jsonl").read_text()


def test_check_network_logs_notification_failure_when_recovery_fails(
    tmp_path: Path,
    monkeypatch,
):
    def fake_recovery(command: str, *, timeout_seconds: float):
        return SimpleNamespace(
            command=command,
            ok=False,
            returncode=1,
            error="boom",
            stderr="",
        )

    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: False)
    monkeypatch.setattr("boring.runtime.run_network_recovery", fake_recovery)
    config = BoxConfig(
        network_check_seconds=1,
        network_recovery_command="systemctl restart NetworkManager",
        network_recovery_cooldown_seconds=300,
    )
    state = RuntimeState(last_network_check=-10)
    network = _FakeNetwork([NetworkStatus(False, "probe", "down")])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_network(0, network, state, config, event_log)

    events = (tmp_path / "events.jsonl").read_text()
    assert "network_recovery_attempted" in events
    assert "notification_failed" in events
    assert "systemctl restart NetworkManager" in events


def test_check_disk_notifies_low_then_recovered(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(disk_min_free_mb=512, disk_check_seconds=1)
    state = RuntimeState(last_disk_check=-10)
    disk = _FakeDisk(
        [
            DiskStatus("/var/lib/boring", 200, 10_000),
            DiskStatus("/var/lib/boring", 800, 10_000),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_disk(0, disk, state, config, event_log)
    assert state.disk_low_alert_sent is True
    _check_disk(2, disk, state, config, event_log)

    assert calls[0][0] == "Boring Box — stockage faible"
    assert calls[0][2] is True
    assert calls[1][0] == "Boring Box — stockage OK"
    assert state.disk_low_alert_sent is False
    events = (tmp_path / "events.jsonl").read_text()
    assert "disk_low" in events
    assert "disk_recovered" in events


def test_check_disk_logs_notification_failure_when_low(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: False)
    config = BoxConfig(disk_min_free_mb=512, disk_check_seconds=1)
    state = RuntimeState(last_disk_check=-10)
    disk = _FakeDisk([DiskStatus("/var/lib/boring", 200, 10_000)])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_disk(0, disk, state, config, event_log)

    events = (tmp_path / "events.jsonl").read_text()
    assert "disk_low" in events
    assert "notification_failed" in events
    assert "/var/lib/boring" in events


def test_current_inference_fps_uses_low_power_when_any_saver_active():
    config = BoxConfig(inference_fps=4, low_power_inference_fps=0.5)

    assert _current_inference_fps(RuntimeState(), config) == 4
    assert _current_inference_fps(RuntimeState(battery_saver_active=True), config) == 0.5
    assert _current_inference_fps(RuntimeState(thermal_saver_active=True), config) == 0.5


def test_check_power_enables_low_power_mode_on_low_battery(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: None)
    config = BoxConfig(
        battery_low_percent=25,
        power_check_seconds=1,
        inference_fps=5,
        low_power_inference_fps=1,
    )
    state = RuntimeState(last_power_check=-10)
    power = _FakePower(
        [
            BatteryStatus(20, False, "bat"),
            BatteryStatus(30, True, "bat"),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)
    assert state.battery_saver_active is True
    assert _current_inference_fps(state, config) == 1
    _check_power(2, power, state, config, event_log)

    assert state.battery_saver_active is False
    assert _current_inference_fps(state, config) == 5
    events = (tmp_path / "events.jsonl").read_text()
    assert events.count("power_saver_changed") == 2


def test_check_power_rearms_alerts_after_recovery_threshold(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(
        battery_low_percent=25,
        battery_recovered_percent=35,
        power_check_seconds=1,
    )
    state = RuntimeState(last_power_check=-10)
    power = _FakePower(
        [
            BatteryStatus(20, False, "bat"),
            BatteryStatus(30, False, "bat"),
            BatteryStatus(36, False, "bat"),
            BatteryStatus(24, False, "bat"),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)
    assert state.battery_critical_active is False
    _check_power(2, power, state, config, event_log)
    assert state.low_battery_alert_sent is True
    _check_power(4, power, state, config, event_log)
    assert state.low_battery_alert_sent is False
    _check_power(6, power, state, config, event_log)

    assert [call[0] for call in calls] == [
        "Boring Box — batterie faible",
        "Boring Box — batterie revenue",
        "Boring Box — batterie faible",
    ]
    events = (tmp_path / "events.jsonl").read_text()
    assert events.count("battery_low") == 2
    assert "battery_recovered" in events


def test_check_power_tracks_critical_battery_until_recovery(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: None)
    config = BoxConfig(
        battery_critical_percent=10,
        battery_recovered_percent=35,
        power_check_seconds=1,
    )
    state = RuntimeState(last_power_check=-10)
    power = _FakePower(
        [
            BatteryStatus(8, False, "bat"),
            BatteryStatus(40, False, "bat"),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)
    assert state.battery_critical_active is True
    _check_power(2, power, state, config, event_log)

    assert state.battery_critical_active is False
    events = (tmp_path / "events.jsonl").read_text()
    assert "battery_critical" in events
    assert "battery_recovered" in events


def test_check_power_logs_notification_failure_for_low_battery(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: False)
    config = BoxConfig(battery_low_percent=25, power_check_seconds=1)
    state = RuntimeState(last_power_check=-10)
    power = _FakePower([BatteryStatus(20, False, "bat")])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)

    events = (tmp_path / "events.jsonl").read_text()
    assert "battery_low" in events
    assert "notification_failed" in events


def test_check_power_does_not_alert_low_battery_while_charging(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr("boring.runtime.notify", lambda *args, **kwargs: calls.append(args))
    config = BoxConfig(battery_low_percent=25, power_check_seconds=1)
    state = RuntimeState(last_power_check=-10)
    power = _FakePower([BatteryStatus(20, True, "bat")])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)

    assert calls == []
    assert state.low_battery_alert_sent is False
    assert not (tmp_path / "events.jsonl").exists()


def test_check_power_blocks_when_battery_sensor_is_missing(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(power_check_seconds=1)
    state = RuntimeState(last_power_check=-10)
    power = _FakePower([None, None])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)
    _check_power(2, power, state, config, event_log)

    assert state.battery_critical_active is True
    assert state.battery_saver_active is True
    assert state.battery_sensor_missing_alert_sent is True
    assert calls == [
        (
            "Boring Box — jauge batterie absente",
            "Autopaiement bloque jusqu'au retour de la jauge.",
            True,
        )
    ]
    assert (tmp_path / "events.jsonl").read_text().count("battery_sensor_missing") == 1


def test_check_power_logs_battery_sensor_recovery(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(power_check_seconds=1)
    state = RuntimeState(last_power_check=-10)
    power = _FakePower([None, BatteryStatus(80, True, "bat")])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_power(0, power, state, config, event_log)
    _check_power(2, power, state, config, event_log)

    assert state.battery_sensor_missing_alert_sent is False
    assert state.battery_critical_active is False
    assert state.battery_saver_active is False
    assert calls[1] == ("Boring Box — jauge batterie revenue", "80% restants", False)
    events = (tmp_path / "events.jsonl").read_text()
    assert "battery_sensor_missing" in events
    assert "battery_sensor_recovered" in events


def test_check_thermal_notifies_warning_then_recovered(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(thermal_warning_c=70, thermal_critical_c=85, thermal_check_seconds=1)
    state = RuntimeState(last_thermal_check=-10)
    thermal = _FakeThermal(
        [
            ThermalStatus(76.2, "/sys/class/thermal/thermal_zone0", "cpu-thermal"),
            ThermalStatus(62.0, "/sys/class/thermal/thermal_zone0", "cpu-thermal"),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_thermal(0, thermal, state, config, event_log)
    assert state.thermal_warning_alert_sent is True
    assert state.thermal_saver_active is True
    _check_thermal(2, thermal, state, config, event_log)

    assert calls[0][0] == "Boring Box — temperature elevee"
    assert calls[0][2] is True
    assert calls[1][0] == "Boring Box — temperature revenue"
    assert state.thermal_warning_alert_sent is False
    assert state.thermal_saver_active is False
    events = (tmp_path / "events.jsonl").read_text()
    assert "thermal_warning" in events
    assert "thermal_recovered" in events


def test_check_thermal_notifies_critical_once(tmp_path: Path, monkeypatch):
    calls = []

    def fake_notify(title: str, message: str, sound: bool = True) -> None:
        calls.append((title, message, sound))

    monkeypatch.setattr("boring.runtime.notify", fake_notify)
    config = BoxConfig(thermal_warning_c=70, thermal_critical_c=85, thermal_check_seconds=1)
    state = RuntimeState(last_thermal_check=-10)
    thermal = _FakeThermal(
        [
            ThermalStatus(87.4, "/sys/class/thermal/thermal_zone0"),
            ThermalStatus(89.0, "/sys/class/thermal/thermal_zone0"),
        ]
    )
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_thermal(0, thermal, state, config, event_log)
    _check_thermal(2, thermal, state, config, event_log)

    assert calls == [("Boring Box — temperature critique", "87.4C", True)]
    assert state.thermal_critical_alert_sent is True
    assert (tmp_path / "events.jsonl").read_text().count("thermal_critical") == 1


def test_check_thermal_logs_notification_failure_when_critical(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("boring.runtime.notify", lambda *_, **__: False)
    config = BoxConfig(thermal_warning_c=70, thermal_critical_c=85, thermal_check_seconds=1)
    state = RuntimeState(last_thermal_check=-10)
    thermal = _FakeThermal([ThermalStatus(87.4, "/sys/class/thermal/thermal_zone0")])
    event_log = EventLog(tmp_path / "events.jsonl")

    _check_thermal(0, thermal, state, config, event_log)

    events = (tmp_path / "events.jsonl").read_text()
    assert "thermal_critical" in events
    assert "notification_failed" in events
    assert "87.4" in events


def test_heartbeat_logs_runtime_activity(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "boring.runtime.notify",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    config = BoxConfig(heartbeat_seconds=30, inference_fps=2)
    state = RuntimeState(last_heartbeat=-60)
    event_log = EventLog(tmp_path / "events.jsonl")

    _heartbeat(0, state, config, event_log)

    assert calls == [
        (("Boring Box — alive", "Service actif, detection en cours."), {"sound": False})
    ]
    events = (tmp_path / "events.jsonl").read_text()
    assert "heartbeat" in events
    assert '"inference_fps": 2' in events


class _FakeNetwork:
    def __init__(self, statuses: list[NetworkStatus]) -> None:
        self.statuses = statuses

    def check(self) -> NetworkStatus:
        return self.statuses.pop(0)


class _FakePower:
    def __init__(self, statuses: list[BatteryStatus | None]) -> None:
        self.statuses = statuses

    def read(self) -> BatteryStatus | None:
        return self.statuses.pop(0)


class _FakeDisk:
    def __init__(self, statuses: list[DiskStatus]) -> None:
        self.statuses = statuses

    def check(self) -> DiskStatus:
        return self.statuses.pop(0)


class _FakeThermal:
    def __init__(self, statuses: list[ThermalStatus]) -> None:
        self.statuses = statuses

    def read(self) -> ThermalStatus:
        return self.statuses.pop(0)
