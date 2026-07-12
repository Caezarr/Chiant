"""Preuve locale que le canal de notification repond."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class NotificationTestReport:
    passed: bool
    webhook_host: str
    status_code: int | None
    title: str
    message: str
    tested_at: str
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_notification_test(
    *,
    webhook_url: str | None,
    title: str = "Boring Box - test notification",
    message: str = "Canal notification pret pour batterie faible.",
    sound: bool = True,
    timeout: float = 5.0,
    post: Callable | None = None,
) -> NotificationTestReport:
    tested_at = datetime.now(timezone.utc).isoformat()
    if not webhook_url:
        return NotificationTestReport(
            passed=False,
            webhook_host="",
            status_code=None,
            title=title,
            message=message,
            tested_at=tested_at,
            error="missing webhook url",
        )

    parsed = urlparse(webhook_url)
    webhook_host = parsed.netloc or "unknown"
    poster = post or httpx.post
    try:
        response = poster(
            webhook_url,
            json={"title": title, "message": message, "sound": sound},
            timeout=timeout,
        )
        status_code = int(getattr(response, "status_code"))
    except Exception as exc:
        return NotificationTestReport(
            passed=False,
            webhook_host=webhook_host,
            status_code=None,
            title=title,
            message=message,
            tested_at=tested_at,
            error=str(exc),
        )

    return NotificationTestReport(
        passed=200 <= status_code < 300,
        webhook_host=webhook_host,
        status_code=status_code,
        title=title,
        message=message,
        tested_at=tested_at,
        error=None if 200 <= status_code < 300 else f"HTTP {status_code}",
    )


def write_report(report: NotificationTestReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
