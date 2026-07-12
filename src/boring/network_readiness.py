"""Runtime network readiness check for a Boring Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from boring.network import NetworkMonitor, NetworkStatus


@dataclass(frozen=True)
class NetworkCheckReport:
    passed: bool
    target: str
    online: bool
    timeout_seconds: float
    recovery_command_configured: bool
    recovery_command: str | None
    checked_at: str
    failures: list[str]
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_network_check(
    *,
    target: str = "1.1.1.1:443",
    timeout_seconds: float = 3.0,
    recovery_command: str | None = None,
    monitor_factory: Callable[[str, float], NetworkMonitor] = NetworkMonitor,
    now: datetime | None = None,
) -> NetworkCheckReport:
    monitor = monitor_factory(target, timeout_seconds)
    status = monitor.check()
    recovery_command = (recovery_command or "").strip() or None
    recovery_configured = recovery_command is not None
    checked_at = (now or datetime.now(timezone.utc)).isoformat()
    failures = _network_failures(status, recovery_command_configured=recovery_configured)
    return NetworkCheckReport(
        passed=not failures,
        target=status.target,
        online=status.online,
        timeout_seconds=timeout_seconds,
        recovery_command_configured=recovery_configured,
        recovery_command=recovery_command,
        checked_at=checked_at,
        failures=failures,
        error=status.error,
    )


def write_report(report: NetworkCheckReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _network_failures(
    status: NetworkStatus,
    *,
    recovery_command_configured: bool,
) -> list[str]:
    failures = []
    if not status.online:
        failures.append("online=false")
    if not recovery_command_configured:
        failures.append("recovery_command=missing")
    return failures
