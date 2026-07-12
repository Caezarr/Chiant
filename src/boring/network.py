"""Monitoring reseau minimal pour la box."""

from __future__ import annotations

import shlex
import socket
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkStatus:
    online: bool
    target: str
    error: str | None = None


@dataclass(frozen=True)
class NetworkRecoveryResult:
    attempted: bool
    ok: bool
    command: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class NetworkMonitor:
    def __init__(self, target: str = "1.1.1.1:443", timeout_seconds: float = 3.0) -> None:
        self.target = target
        self.timeout_seconds = timeout_seconds

    def check(self) -> NetworkStatus:
        host, port = parse_target(self.target)
        try:
            with socket.create_connection((host, port), timeout=self.timeout_seconds):
                return NetworkStatus(online=True, target=self.target)
        except OSError as exc:
            return NetworkStatus(online=False, target=self.target, error=str(exc))


def parse_target(target: str) -> tuple[str, int]:
    if ":" not in target:
        return target, 443
    host, port = target.rsplit(":", 1)
    return host, int(port)


def run_network_recovery(
    command: str | None, *, timeout_seconds: float = 20.0
) -> NetworkRecoveryResult:
    command = (command or "").strip()
    if not command:
        return NetworkRecoveryResult(attempted=False, ok=False, command="")
    try:
        args = shlex.split(command)
    except ValueError as exc:
        return NetworkRecoveryResult(
            attempted=True,
            ok=False,
            command=command,
            error=str(exc),
        )
    if not args:
        return NetworkRecoveryResult(attempted=False, ok=False, command="")
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return NetworkRecoveryResult(
            attempted=True,
            ok=False,
            command=command,
            error=str(exc),
        )
    return NetworkRecoveryResult(
        attempted=True,
        ok=completed.returncode == 0,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )
