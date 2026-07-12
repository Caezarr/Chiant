"""Runtime systemd readiness check for an installed Boring Box service."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SystemdCheckReport:
    service: str
    passed: bool
    enabled_state: str | None
    active_state: str | None
    sub_state: str | None
    unit_file_state: str | None
    type: str | None
    watchdog_usec: int | None
    main_pid: int | None
    n_restarts: int | None
    exec_start: str | None
    user: str | None
    checked_at: str
    failures: list[str]
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_systemd_check(
    service: str = "boring-box.service",
    *,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
) -> SystemdCheckReport:
    """Inspect the installed systemd unit state on a Pi-like host."""
    execute = runner or _run_command
    checked_at = (now or datetime.now(timezone.utc)).isoformat()
    enabled_state: str | None = None
    active_state: str | None = None
    properties: dict[str, str] = {}
    errors: list[str] = []

    enabled = execute(["systemctl", "is-enabled", service])
    if enabled.returncode == 0:
        enabled_state = enabled.stdout.strip() or None
    else:
        enabled_state = enabled.stdout.strip() or None
        errors.append(_command_error("is-enabled", enabled))

    active = execute(["systemctl", "is-active", service])
    if active.returncode == 0:
        active_state = active.stdout.strip() or None
    else:
        active_state = active.stdout.strip() or None
        errors.append(_command_error("is-active", active))

    shown = execute(
        [
            "systemctl",
            "show",
            service,
            "--property=ActiveState,SubState,UnitFileState,Type,WatchdogUSec,MainPID,NRestarts,ExecStart,User",
            "--no-pager",
        ]
    )
    if shown.returncode == 0:
        properties = _parse_systemctl_show(shown.stdout)
    else:
        errors.append(_command_error("show", shown))

    active_state = properties.get("ActiveState") or active_state
    watchdog_usec = _int_or_none(properties.get("WatchdogUSec"))
    main_pid = _int_or_none(properties.get("MainPID"))
    n_restarts = _int_or_none(properties.get("NRestarts"))
    failures = _systemd_failures(
        enabled_state=enabled_state,
        active_state=active_state,
        sub_state=properties.get("SubState"),
        unit_file_state=properties.get("UnitFileState"),
        service_type=properties.get("Type"),
        watchdog_usec=watchdog_usec,
        main_pid=main_pid,
        n_restarts=n_restarts,
        exec_start=properties.get("ExecStart"),
        user=properties.get("User"),
    )
    error = "; ".join(errors) if errors else None
    return SystemdCheckReport(
        service=service,
        passed=not failures and error is None,
        enabled_state=enabled_state,
        active_state=active_state,
        sub_state=properties.get("SubState"),
        unit_file_state=properties.get("UnitFileState"),
        type=properties.get("Type"),
        watchdog_usec=watchdog_usec,
        main_pid=main_pid,
        n_restarts=n_restarts,
        exec_start=properties.get("ExecStart"),
        user=properties.get("User"),
        checked_at=checked_at,
        failures=failures,
        error=error,
    )


def write_report(report: SystemdCheckReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True)


def _parse_systemctl_show(output: str) -> dict[str, str]:
    properties = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key] = value
    return properties


def _systemd_failures(
    *,
    enabled_state: str | None,
    active_state: str | None,
    sub_state: str | None,
    unit_file_state: str | None,
    service_type: str | None,
    watchdog_usec: int | None,
    main_pid: int | None,
    n_restarts: int | None,
    exec_start: str | None,
    user: str | None,
) -> list[str]:
    failures = []
    if enabled_state != "enabled":
        failures.append(f"enabled={enabled_state or '-'}")
    if active_state != "active":
        failures.append(f"active={active_state or '-'}")
    if sub_state != "running":
        failures.append(f"sub={sub_state or '-'}")
    if unit_file_state != "enabled":
        failures.append(f"unit_file={unit_file_state or '-'}")
    if service_type != "notify":
        failures.append(f"type={service_type or '-'}")
    if watchdog_usec is None or watchdog_usec <= 0:
        failures.append(f"watchdog_usec={watchdog_usec or 0}")
    if main_pid is None or main_pid <= 0:
        failures.append(f"main_pid={main_pid or 0}")
    if n_restarts is None:
        failures.append("n_restarts=-")
    elif n_restarts != 0:
        failures.append(f"n_restarts={n_restarts}")
    if "boring box-run" not in (exec_start or ""):
        failures.append("exec_start")
    if user != "boring":
        failures.append(f"user={user or '-'}")
    return failures


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _command_error(name: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    return f"systemctl {name} exited {result.returncode}: {detail or '-'}"
