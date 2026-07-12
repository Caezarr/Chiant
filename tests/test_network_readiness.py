from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boring.network import NetworkStatus
from boring.network_readiness import run_network_check, write_report


def test_network_check_passes_when_online_and_recovery_configured():
    report = run_network_check(
        target="1.1.1.1:443",
        recovery_command="systemctl restart NetworkManager",
        monitor_factory=lambda target, timeout: _StaticMonitor(NetworkStatus(True, target)),
        now=_now(),
    )

    assert report.passed is True
    assert report.online is True
    assert report.recovery_command_configured is True
    assert report.recovery_command == "systemctl restart NetworkManager"
    assert report.failures == []


def test_network_check_fails_when_offline():
    report = run_network_check(
        target="1.1.1.1:443",
        recovery_command="systemctl restart NetworkManager",
        monitor_factory=lambda target, timeout: _StaticMonitor(
            NetworkStatus(False, target, error="timeout")
        ),
    )

    assert report.passed is False
    assert "online=false" in report.failures
    assert report.error == "timeout"


def test_network_check_fails_without_recovery_command():
    report = run_network_check(
        target="1.1.1.1:443",
        recovery_command="",
        monitor_factory=lambda target, timeout: _StaticMonitor(NetworkStatus(True, target)),
    )

    assert report.passed is False
    assert "recovery_command=missing" in report.failures
    assert report.recovery_command is None


def test_write_network_report_includes_passed(tmp_path: Path):
    report = run_network_check(
        recovery_command="systemctl restart NetworkManager",
        monitor_factory=lambda target, timeout: _StaticMonitor(NetworkStatus(True, target)),
        now=_now(),
    )
    output = tmp_path / "reports" / "network-check.json"

    write_report(report, output)

    assert '"passed": true' in output.read_text()


class _StaticMonitor:
    def __init__(self, status: NetworkStatus) -> None:
        self.status = status

    def check(self) -> NetworkStatus:
        return self.status


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
