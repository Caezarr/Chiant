"""Surveillance espace disque pour boitier headless."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskStatus:
    path: str
    free_mb: int
    total_mb: int


class DiskSpaceMonitor:
    def __init__(self, path: Path) -> None:
        self.path = path

    def check(self) -> DiskStatus | None:
        target = self.path if self.path.exists() else self.path.parent
        try:
            usage = shutil.disk_usage(target)
        except OSError:
            return None
        return DiskStatus(
            path=str(target),
            free_mb=usage.free // 1_000_000,
            total_mb=usage.total // 1_000_000,
        )
