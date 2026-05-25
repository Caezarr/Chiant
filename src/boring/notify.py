"""Notifications macOS (osascript) avec fallback console."""

from __future__ import annotations

import shlex
import subprocess
import sys

from rich.console import Console

console = Console()


def notify(title: str, message: str, sound: bool = True) -> None:
    """Envoie une notif macOS. Fallback : print console."""
    if sys.platform != "darwin":
        console.print(f"[yellow]NOTIF[/yellow] {title} — {message}")
        return
    script = (
        f"display notification {shlex.quote(message)} "
        f"with title {shlex.quote(title)}"
    )
    if sound:
        script += ' sound name "Ping"'
    subprocess.run(["osascript", "-e", script], check=False)
    console.print(f"[green]NOTIF[/green] {title} — {message}")
