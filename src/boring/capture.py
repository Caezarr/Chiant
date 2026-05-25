"""Capture webcam : preview interactif ou capture auto pour collecte dataset."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterator

import cv2
from rich.console import Console

console = Console()


def open_camera(device_index: int = 0) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        raise RuntimeError(f"Impossible d'ouvrir la caméra (index={device_index})")
    return cap


def iter_frames(
    device_index: int = 0,
    fps: float | None = None,
) -> Iterator[tuple[float, "cv2.Mat"]]:
    """Itère sur les frames de la webcam. fps=None → max disponible."""
    cap = open_camera(device_index)
    interval = 1.0 / fps if fps else 0.0
    last_emit = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                console.print("[red]Échec lecture frame.[/red]")
                break
            now = time.time()
            if interval == 0 or now - last_emit >= interval:
                last_emit = now
                yield now, frame
    finally:
        cap.release()


def capture_interactive(output_dir: Path, device_index: int = 0) -> None:
    """Preview live + SPACE pour sauver une frame, Q pour quitter."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = open_camera(device_index)
    console.print(
        f"[green]Capture interactive[/green] → [bold]{output_dir}[/bold]\n"
        "[dim]SPACE = sauver une frame, Q = quitter[/dim]"
    )
    n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imshow("Boring — capture (SPACE save, Q quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                path = output_dir / f"frame_{int(time.time() * 1000)}.jpg"
                cv2.imwrite(str(path), frame)
                n += 1
                console.print(f"[cyan]→ {path.name}[/cyan]")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    console.print(f"[green]Terminé.[/green] {n} frames sauvées.")


def capture_auto(
    output_dir: Path,
    device_index: int = 0,
    interval_seconds: float = 1.0,
    max_frames: int | None = None,
) -> None:
    """Capture automatique sans preview, 1 frame toutes les N secondes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fps = 1.0 / interval_seconds
    n = 0
    console.print(
        f"[green]Capture auto[/green] (1 frame / {interval_seconds}s) → [bold]{output_dir}[/bold]\n"
        "[dim]Ctrl+C pour stopper[/dim]"
    )
    try:
        for ts, frame in iter_frames(device_index=device_index, fps=fps):
            path = output_dir / f"frame_{int(ts * 1000)}.jpg"
            cv2.imwrite(str(path), frame)
            n += 1
            if n % 10 == 0:
                console.print(f"[dim]… {n} frames[/dim]")
            if max_frames and n >= max_frames:
                break
    except KeyboardInterrupt:
        pass
    console.print(f"[green]Terminé.[/green] {n} frames sauvées.")
