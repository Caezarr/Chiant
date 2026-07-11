"""Integration minimale avec systemd notify/watchdog."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SystemdNotifier:
    notify_socket: str | None
    watchdog_usec: int | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SystemdNotifier":
        values = env or os.environ
        watchdog_raw = values.get("WATCHDOG_USEC")
        watchdog_usec = None
        if watchdog_raw:
            try:
                watchdog_usec = int(watchdog_raw)
            except ValueError:
                watchdog_usec = None
        return cls(values.get("NOTIFY_SOCKET"), watchdog_usec=watchdog_usec)

    @property
    def enabled(self) -> bool:
        return bool(self.notify_socket)

    def watchdog_interval_seconds(self, default: float = 30.0) -> float:
        if not self.watchdog_usec or self.watchdog_usec <= 0:
            return default
        return max(1.0, self.watchdog_usec / 2_000_000)

    def ready(self, status: str = "ready") -> bool:
        return self.notify(f"READY=1\nSTATUS={status}")

    def watchdog(self, status: str = "alive") -> bool:
        return self.notify(f"WATCHDOG=1\nSTATUS={status}")

    def stopping(self) -> bool:
        return self.notify("STOPPING=1")

    def notify(self, message: str) -> bool:
        if not self.notify_socket:
            return False
        address = _systemd_address(self.notify_socket)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.connect(address)
                sock.sendall(message.encode("utf-8"))
            return True
        except OSError:
            return False


def _systemd_address(raw: str) -> str:
    if raw.startswith("@"):
        return "\0" + raw[1:]
    return raw
