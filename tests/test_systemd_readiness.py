from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from boring.systemd_readiness import run_systemd_check, write_report


def test_systemd_check_passes_for_installed_running_service():
    report = run_systemd_check(runner=_fake_runner(), now=_now())

    assert report.passed is True
    assert report.enabled_state == "enabled"
    assert report.active_state == "active"
    assert report.sub_state == "running"
    assert report.watchdog_usec == 30_000_000
    assert report.main_pid == 1234
    assert report.n_restarts == 0
    assert report.failures == []


def test_systemd_check_fails_when_service_is_inactive():
    report = run_systemd_check(runner=_fake_runner(active="inactive", sub="dead"))

    assert report.passed is False
    assert "active=inactive" in report.failures
    assert "sub=dead" in report.failures


def test_systemd_check_records_command_errors():
    report = run_systemd_check(runner=_fake_runner(enabled="disabled", enabled_error=True))

    assert report.passed is False
    assert report.error is not None
    assert "is-enabled exited 1" in report.error
    assert "enabled=disabled" in report.failures


def test_systemd_check_fails_without_main_pid():
    report = run_systemd_check(runner=_fake_runner(main_pid=0))

    assert report.passed is False
    assert "main_pid=0" in report.failures


def test_systemd_check_fails_after_watchdog_restarts():
    report = run_systemd_check(runner=_fake_runner(n_restarts=2))

    assert report.passed is False
    assert "n_restarts=2" in report.failures


def test_write_systemd_report_includes_passed(tmp_path: Path):
    report = run_systemd_check(runner=_fake_runner(), now=_now())
    output = tmp_path / "reports" / "systemd-check.json"

    write_report(report, output)

    assert '"passed": true' in output.read_text()


def _fake_runner(
    *,
    enabled: str = "enabled",
    active: str = "active",
    sub: str = "running",
    main_pid: int = 1234,
    n_restarts: int = 0,
    enabled_error: bool = False,
):
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        action = command[1]
        if action == "is-enabled":
            return subprocess.CompletedProcess(
                command,
                1 if enabled_error else 0,
                stdout=f"{enabled}\n",
                stderr="not enabled\n" if enabled_error else "",
            )
        if action == "is-active":
            return subprocess.CompletedProcess(
                command, 0 if active == "active" else 3, stdout=f"{active}\n"
            )
        if action == "show":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="\n".join(
                    [
                        f"ActiveState={active}",
                        f"SubState={sub}",
                        f"UnitFileState={enabled}",
                        "Type=notify",
                        "WatchdogUSec=30000000",
                        f"MainPID={main_pid}",
                        f"NRestarts={n_restarts}",
                        "ExecStart={ path=/opt/boring/.venv/bin/boring ; argv[]=/opt/boring/.venv/bin/boring box-run ; }",
                        "User=boring",
                    ]
                ),
            )
        raise AssertionError(f"unexpected command: {command}")

    return run


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)
