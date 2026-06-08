"""CLI Boring."""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

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
    ai: bool = typer.Option(True, help="Utiliser Claude API pour générer le courrier."),
    live: bool = typer.Option(False, help="Appel réel à Claude (désactive dry_run)."),
    evidence: list[Path] = typer.Option(
        default_factory=list,
        help="Chemins vers les pièces justificatives (photos, PDF). Répétable.",
    ),
) -> None:
    """Génère un RAPO (Recours Administratif Préalable Obligatoire) pour un FPS."""
    if live:
        console.print("[bold]Appel Claude API en cours...[/bold]")
    client = RAPOContestClient(dry_run=not live, use_ai=ai)
    case = client.prepare_case(
        user_id="cli-user",
        subject=subject,
        reason=reason,
        amount_eur=amount,
        evidence_paths=evidence,
    )
    console.print(f"[green]✓[/green] Cas {case.case_id} prêt")
    if output:
        path = Path(output)
        path.write_text(case.drafted_letter or "")
        console.print(f"[green]✓[/green] Courrier sauvegardé : {path}")
        if evidence:
            console.print(f"  Pièces : {', '.join(p.name for p in evidence)}")
    else:
        console.print("\n[dim]--- Courrier généré ---[/dim]")
        console.print(case.drafted_letter)


@app.command()
def status(
    plate: str = typer.Option(None, envvar="DEFAULT_VEHICLE_PLATE", help="Plaque à vérifier."),
) -> None:
    """Vérifie s'il y a une session de stationnement active."""
    try:
        provider = make_payment_provider()
        provider.login("", "")
        session = provider.get_active_session(plate or "")
        if session is None:
            console.print("[yellow]Aucune session active.[/yellow]")
            return
        table = Table(title="Session active")
        table.add_column("Champ", style="bold")
        table.add_column("Valeur")
        table.add_row("Provider", provider.name)
        table.add_row("Session ID", str(session.session_id))
        table.add_row("Plaque", str(session.vehicle_plate))
        table.add_row("Fin prévue", session.end.strftime("%Y-%m-%d %H:%M"))
        if hasattr(session, "amount") and session.amount and session.amount > 0:
            table.add_row("Montant", f"{session.amount:.2f} €")
        console.print(table)
    except Exception as e:
        console.print(f"[red]Erreur : {e}[/red]")


@app.command()
def scrape(
    output: Path = typer.Option(Path("datasets/baseline"), help="Dossier de sortie."),
    count: int = typer.Option(30, help="Images cibles par requête."),
) -> None:
    """Scrape des images de véhicules LAPI depuis DuckDuckGo pour le dataset baseline."""
    project_root = Path(__file__).resolve().parents[3]
    script_path = project_root / "scripts" / "scrape_baseline.py"
    if not script_path.exists():
        console.print(f"[red]Erreur : script introuvable : {script_path}[/red]")
        raise typer.Exit(1)
    console.print(f"[bold]Scraping vers {output} ({count} images cibles)...[/bold]")
    result = subprocess.run(
        ["uv", "run", "python", str(script_path), "--output", str(output), "--count", str(count)],
        check=False,
        cwd=project_root,
    )
    if result.returncode != 0:
        console.print("[red]Le script de scraping s'est terminé avec une erreur.[/red]")
        raise typer.Exit(result.returncode)


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


@app.command("setup-paybyphone")
def setup_paybyphone(
    endpoints: Path = typer.Option(
        Path("scripts/paybyphone_endpoints.json"),
        help="JSON généré par parse_paybyphone_har.py",
    ),
    patch_env: bool = typer.Option(True, help="Patch .env avec les config_hints extraits."),
) -> None:
    """Configure le client PayByPhone depuis l'export HAR (paybyphone_endpoints.json)."""
    if not endpoints.exists():
        console.print(
            f"[red]Fichier introuvable : {endpoints}[/red]\n"
            "[dim]Lance d'abord :[/dim]\n"
            "  uv run python scripts/parse_paybyphone_har.py scripts/pbp.har\n"
            "pour générer ce fichier depuis ton export HAR."
        )
        raise typer.Exit(1)

    try:
        data = json.loads(endpoints.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        console.print(f"[red]Impossible de lire {endpoints} : {exc}[/red]")
        raise typer.Exit(1)

    if not isinstance(data, dict) or "config_hints" not in data:
        console.print(
            "[yellow]Pas de config_hints dans ce fichier.[/yellow]\n"
            "[dim]Regénère-le avec une version récente de parse_paybyphone_har.py.[/dim]"
        )
        raise typer.Exit(1)

    hints: dict = data["config_hints"]

    # Affichage du tableau des hints
    table = Table(title="PayByPhone — config hints")
    table.add_column("Clé", style="bold")
    table.add_column("Valeur")
    found: dict[str, str] = {}
    for key, value in hints.items():
        if value is not None:
            table.add_row(key, str(value))
            found[key] = str(value)
        else:
            table.add_row(key, "[yellow]non trouvé[/yellow]")
    console.print(table)

    if not found:
        console.print("[yellow]Aucun hint exploitable — .env non modifié.[/yellow]")
        raise typer.Exit(0)

    if patch_env:
        env_path = Path(".env")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        env_mapping = {
            "PAYBYPHONE_API_BASE": hints.get("base_url"),
            "PAYBYPHONE_AUTH_URL": hints.get("auth_url"),
            "PAYBYPHONE_CLIENT_ID": hints.get("client_id"),
        }
        lines = [f"\n# Auto-patch depuis HAR — {timestamp}\n"]
        patched: list[str] = []
        for var, val in env_mapping.items():
            if val is not None:
                lines.append(f"{var}={val}\n")
                patched.append(var)

        with env_path.open("a") as f:
            f.writelines(lines)

        if patched:
            console.print(
                f"\n[green]✓[/green] {len(patched)} variable(s) ajoutée(s) dans {env_path} :"
            )
            for var in patched:
                console.print(f"  [dim]{var}[/dim]")
        else:
            console.print("[yellow]Aucune variable à écrire (hints base_url/auth_url/client_id absents).[/yellow]")

    console.print("\n[bold green]Setup PayByPhone terminé.[/bold green]")


if __name__ == "__main__":
    app()
