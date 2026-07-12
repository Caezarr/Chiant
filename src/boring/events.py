"""Journal local d'evenements production."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, path: Path, max_bytes: int = 5_000_000, backups: int = 3) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups

    def write(self, event: str, **payload: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        self._rotate_if_needed(len(line.encode("utf-8")))
        with self.path.open("a") as f:
            f.write(line)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if self.max_bytes <= 0 or self.backups <= 0 or not self.path.exists():
            return
        try:
            current_size = self.path.stat().st_size
        except OSError:
            return
        if current_size + incoming_bytes <= self.max_bytes:
            return
        oldest = self.path.with_name(f"{self.path.name}.{self.backups}")
        oldest.unlink(missing_ok=True)
        for index in range(self.backups - 1, 0, -1):
            src = self.path.with_name(f"{self.path.name}.{index}")
            dst = self.path.with_name(f"{self.path.name}.{index + 1}")
            if src.exists():
                src.replace(dst)
        self.path.replace(self.path.with_name(f"{self.path.name}.1"))
