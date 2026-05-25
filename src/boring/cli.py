"""CLI Boring."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from boring import __version__
from boring.capture import capture_auto, capture_interactive
from boring.contest.rapo import RAPOContestClient
from boring.detect import Detector, run_live_detection
from boring.glue import make_payment_provider, run_pipeline

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


@app.command("contest-fps")
def contest_fps(
    subject: str = typer.Option(..., help="Référence du FPS (ex: FPS-2026-LL-12345)."),
    reason: str = typer.Option(..., help="Motif de contestation en 1-2 phrases."),
    amount: float = typer.Option(35.0, help="Montant contesté en €."),
    output: str = typer.Option(None, help="Chemin où sauver le courrier (sinon stdout)."),
) -> None:
    """Génère un RAPO (Recours Administratif Préalable Obligatoire) pour un FPS."""
    client = RAPOContestClient(dry_run=True)
    case = client.prepare_case(
        user_id="cli-user",
        subject=subject,
        reason=reason,
        amount_eur=amount,
    )
    console.print(f"[green]✓[/green] Cas {case.case_id} prêt")
    if output:
        from pathlib import Path

        path = Path(output)
        path.write_text(case.drafted_letter or "")
        console.print(f"[green]✓[/green] Courrier sauvegardé : {path}")
    else:
        console.print("\n[dim]--- Courrier généré ---[/dim]")
        console.print(case.drafted_letter)


@app.command("pay-now")
def pay_now(
    plate: str = typer.Option(..., help="Plaque (ex: AB-123-CD)."),
    duration: int = typer.Option(15, help="Durée en minutes."),
    lat: float = typer.Option(50.6371, help="Latitude (défaut: Place du Théâtre Lille)."),
    lon: float = typer.Option(3.0633, help="Longitude."),
) -> None:
    """Déclenche un paiement immédiat sans détection (test du flow paiement)."""
    provider = make_payment_provider()
    provider.login("", "")
    zone_id = provider.get_zone_id(lat, lon)
    session = provider.start_session(plate, zone_id, duration)
    console.print(f"[green]✓ Session déclenchée[/green] : {session.session_id}")
    console.print(f"  Provider : {provider.name}")
    console.print(f"  Plaque   : {session.vehicle_plate}")
    console.print(f"  Durée    : {duration} min")
    console.print(f"  Fin      : {session.end.strftime('%H:%M')}")


if __name__ == "__main__":
    app()
