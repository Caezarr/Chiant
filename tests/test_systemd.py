from __future__ import annotations

from boring.systemd import SystemdNotifier, _systemd_address


def test_systemd_notifier_from_env_parses_watchdog():
    notifier = SystemdNotifier.from_env(
        {
            "NOTIFY_SOCKET": "/run/systemd/notify",
            "WATCHDOG_USEC": "120000000",
        }
    )

    assert notifier.enabled is True
    assert notifier.watchdog_interval_seconds() == 60


def test_systemd_notifier_disabled_without_socket():
    notifier = SystemdNotifier.from_env({})

    assert notifier.enabled is False
    assert notifier.ready() is False
    assert notifier.watchdog() is False


def test_systemd_address_supports_abstract_namespace():
    assert _systemd_address("@notify") == "\0notify"
    assert _systemd_address("/run/notify") == "/run/notify"


def test_systemd_notify_sends_datagram(monkeypatch):
    sent = {}

    class FakeSocket:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def connect(self, address):
            sent["address"] = address

        def sendall(self, payload):
            sent["payload"] = payload

    monkeypatch.setattr("boring.systemd.socket.socket", FakeSocket)

    ok = SystemdNotifier("@notify").ready("ok")

    assert ok is True
    assert sent["address"] == "\0notify"
    assert sent["payload"] == b"READY=1\nSTATUS=ok"
