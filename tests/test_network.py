from __future__ import annotations

from boring.network import NetworkMonitor, parse_target, run_network_recovery


def test_parse_target_default_port():
    assert parse_target("example.com") == ("example.com", 443)


def test_parse_target_explicit_port():
    assert parse_target("1.1.1.1:443") == ("1.1.1.1", 443)


def test_network_monitor_reports_failure():
    status = NetworkMonitor("127.0.0.1:1", timeout_seconds=0.01).check()

    assert status.online is False
    assert status.target == "127.0.0.1:1"
    assert status.error


def test_run_network_recovery_skips_empty_command():
    result = run_network_recovery("")

    assert result.attempted is False
    assert result.ok is False


def test_run_network_recovery_reports_command_result(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return Completed()

    monkeypatch.setattr("boring.network.subprocess.run", fake_run)

    result = run_network_recovery("systemctl restart NetworkManager")

    assert result.attempted is True
    assert result.ok is True
    assert result.returncode == 0
    assert result.stdout == "ok"
    assert calls[0][0] == ["systemctl", "restart", "NetworkManager"]
