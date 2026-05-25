"""CLI Boring."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from boring import __version__
from boring.capture import capture_auto, capture_interactive
from boring.detect import Detector, run_live_detection
from boring.glue import run_pipeline

app = typer.Typer(help="Boring — paiement intelligent du stationnement.")
console = Console()


@app.command()
def version() -> None:
    """Affiche la version."""
    console.print(f"Boring v{__version__}")


@app.command()
def capture(
    output: Path = typer.Option(Path("frames"), help="Dossier de sortie."),
    auto: bool = typer.Option(False, help="Capture auto sans preview."),
    interval: float = typer.Option(1.0, help="Intervalle (s) en mode auto."),
    max_frames: int = typer.Option(None, help="Limite de frames en mode auto."),
    device: int = typer.Option(0, help="Index du device webcam."),
) -> None:
    """Capture frames depuis la webcam."""
    if auto:
        capture_auto(output, device_index=device, interval_seconds=interval, max_frames=max_frames)
    else:
        capture_interactive(output, device_index=device)


@app.command()
def detect(
    source: str = typer.Option("webcam", help="webcam (vidéo non implémentée)"),
    model: str = typer.Option("yolov8n.pt", help="Modèle YOLO (.pt)"),
    confidence: float = typer.Option(0.5, help="Seuil de confiance."),
    fps: float = typer.Option(5.0, help="FPS d'inférence."),
    target: str = typer.Option("car", help="Labels cibles, séparés par virgule."),
) -> None:
    """Détection live. Baseline COCO 'car' ; après fine-tune : 'scan_car'."""
    if source != "webcam":
        console.print("[yellow]Source vidéo non implémentée.[/yellow]")
        raise typer.Exit(1)
    det = Detector(
        model_path=model,
        target_labels=tuple(t.strip() for t in target.split(",")),
        confidence_threshold=confidence,
    )
    for _ in run_live_detection(det, fps=fps):
        pass


@app.command()
def run(
    lat: float = typer.Option(None, help="Latitude (override géoloc)."),
    lon: float = typer.Option(None, help="Longitude (override géoloc)."),
    fps: float = typer.Option(5.0, help="FPS pipeline."),
) -> None:
    """Pipeline end-to-end : détection → geofence → paiement."""
    run_pipeline(current_lat=lat, current_lon=lon, fps=fps)


if __name__ == "__main__":
    app()
