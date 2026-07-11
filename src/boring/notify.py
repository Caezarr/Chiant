"""Notifications macOS (osascript) avec fallback console."""

from __future__ import annotations

import shlex
import subprocess
import sys

import httpx
from rich.console import Console

console = Console()


def notify(title: str, message: str, sound: bool = True) -> None:
    """Envoie une notif webhook/macOS. Fallback : print console."""
    webhook_url = _webhook_url()
    if webhook_url:
        try:
            httpx.post(
                webhook_url,
                json={"title": title, "message": message, "sound": sound},
                timeout=5,
            ).raise_for_status()
            console.print(f"[green]WEBHOOK[/green] {title} — {message}")
            return
        except httpx.HTTPError as e:
            console.print(f"[yellow]Webhook notif échouée[/yellow] {e}")
    if sys.platform != "darwin":
        console.print(f"[yellow]NOTIF[/yellow] {title} — {message}")
        return
    script = f"display notification {shlex.quote(message)} with title {shlex.quote(title)}"
    if sound:
        script += ' sound name "Ping"'
    subprocess.run(["osascript", "-e", script], check=False)
    console.print(f"[green]NOTIF[/green] {title} — {message}")


def _webhook_url() -> str | None:
    from os import getenv

    return getenv("BORING_NOTIFY_WEBHOOK_URL") or getenv("NTFY_WEBHOOK_URL")
