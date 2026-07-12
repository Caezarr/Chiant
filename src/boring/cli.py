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
from boring.autopay_readiness import audit_autopay_readiness
from boring.autopay_readiness import write_report as write_autopay_report
from boring.autopay_smoke import run_autopay_smoke
from boring.autopay_smoke import write_report as write_autopay_smoke_report
from boring.benchmark import run_vision_benchmark
from boring.benchmark import write_report as write_benchmark_report
from boring.burn_in import BoxBurnInRunner
from boring.camera_readiness import run_camera_check
from boring.camera_readiness import write_report as write_camera_report
from boring.capture import capture_auto, capture_interactive, iter_frames
from boring.config import BoxConfig
from boring.contest.rapo import RAPOContestClient
from boring.detect import Detector, run_live_detection
from boring.evidence_pack import (
    build_evidence_pack,
    default_evidence_paths,
    evidence_item_ok,
    write_pack,
)
from boring.glue import make_payment_provider, run_pipeline
from boring.notification_readiness import run_notification_test
from boring.notification_readiness import write_report as write_notification_report
from boring.position import make_position_provider
from boring.position_readiness import run_position_check
from boring.position_readiness import write_report as write_position_report
from boring.production_readiness import audit_production_readiness
from boring.production_readiness import write_report as write_production_report
from boring.runtime import box_doctor, run_box_service
from boring.systemd_readiness import run_systemd_check
from boring.systemd_readiness import write_report as write_systemd_report
from boring.vision_eval import evaluate_yolo_dataset
from boring.vision_eval import write_report as write_vision_eval_report
from boring.vision_readiness import audit_vision_readiness
from boring.vision_readiness import write_report as write_vision_readiness_report
from boring.vision_sources import load_source_catalog

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


@app.command("box-run")
def box_run() -> None:
    """Lance le service headless Raspberry Pi / box."""
    run_box_service()


@app.command("box-doctor")
def box_doctor_cmd() -> None:
    """Vérifie la config minimale avant de laisser tourner la box."""
    raise typer.Exit(box_doctor())


@app.command("box-burn-in")
def box_burn_in(
    minutes: float = typer.Option(30.0, help="Duree du burn-in en minutes."),
    interval: float = typer.Option(60.0, help="Intervalle entre deux sondes en secondes."),
    output: Path = typer.Option(Path("burn-in"), help="Dossier du rapport."),
) -> None:
    """Sonde camera, batterie, temperature et reseau avant une beta terrain."""
    config = BoxConfig.from_env()
    runner = BoxBurnInRunner(config)
    console.print(
        f"[bold]Burn-in box[/bold] — {minutes:.1f} min, intervalle {interval:.0f}s, sortie {output}"
    )
    report = runner.run(
        duration_seconds=max(0.0, minutes * 60),
        interval_seconds=max(1.0, interval),
        output_dir=output,
    )
    table = Table(title="Boring Box — burn-in report")
    table.add_column("Signal", style="bold")
    table.add_column("Valeur")
    table.add_row("Samples", str(report.sample_count))
    table.add_row("Camera failures", str(report.camera_failures))
    table.add_row("Network failures", str(report.network_failures))
    table.add_row(
        "Battery min",
        "-" if report.min_battery_percent is None else f"{report.min_battery_percent}%",
    )
    table.add_row(
        "Battery delta",
        "-" if report.battery_delta_percent is None else f"{report.battery_delta_percent:+d}%",
    )
    table.add_row("Charging seen", "yes" if report.charging_seen else "no")
    table.add_row("Discharging seen", "yes" if report.discharging_seen else "no")
    table.add_row("Temp max", "-" if report.max_temp_c is None else f"{report.max_temp_c:.1f}C")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output / 'report.json'}[/dim]")
    console.print(f"[dim]Samples: {output / 'samples.jsonl'}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("box-notify-test")
def box_notify_test(
    output: Path = typer.Option(
        Path("reports/notification-test.json"),
        help="Rapport JSON du test notification.",
    ),
    title: str = typer.Option("Boring Box - test notification", help="Titre envoye."),
    message: str = typer.Option(
        "Canal notification pret pour batterie faible.",
        help="Message envoye.",
    ),
) -> None:
    """Teste le webhook notification utilise pour batterie faible."""
    config = BoxConfig.from_env()
    report = run_notification_test(
        webhook_url=config.notify_webhook_url,
        title=title,
        message=message,
    )
    write_notification_report(report, output)
    table = Table(title="Boring Box — notification test")
    table.add_column("Signal", style="bold")
    table.add_column("Valeur")
    table.add_row("Webhook host", report.webhook_host or "-")
    table.add_row("Status code", "-" if report.status_code is None else str(report.status_code))
    table.add_row("Error", report.error or "-")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("box-systemd-check")
def box_systemd_check(
    service: str = typer.Option("boring-box.service", help="Nom du service systemd."),
    output: Path = typer.Option(
        Path("reports/systemd-check.json"),
        help="Rapport JSON du service installe.",
    ),
) -> None:
    """Verifie l'etat runtime du service systemd installe sur le Pi."""
    report = run_systemd_check(service)
    write_systemd_report(report, output)
    table = Table(title="Boring Box — systemd runtime")
    table.add_column("Signal", style="bold")
    table.add_column("Valeur")
    table.add_row("Service", report.service)
    table.add_row("Enabled", report.enabled_state or "-")
    table.add_row("Active", report.active_state or "-")
    table.add_row("Sub", report.sub_state or "-")
    table.add_row("Type", report.type or "-")
    table.add_row(
        "Watchdog usec", "-" if report.watchdog_usec is None else str(report.watchdog_usec)
    )
    table.add_row("User", report.user or "-")
    table.add_row("Failures", ", ".join(report.failures) if report.failures else "-")
    table.add_row("Error", report.error or "-")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("box-position-check")
def box_position_check(
    output: Path = typer.Option(
        Path("reports/position-check.json"),
        help="Rapport JSON de position runtime.",
    ),
) -> None:
    """Verifie que la box obtient une position exploitable pour le geofence."""
    config = BoxConfig.from_env()
    provider = make_position_provider(
        config.position_mode,
        config.lat,
        config.lon,
        config.gpsd_host,
        config.gpsd_port,
    )
    report = run_position_check(
        provider,
        mode=config.position_mode,
        expected_lat=config.lat,
        expected_lon=config.lon,
    )
    write_position_report(report, output)
    table = Table(title="Boring Box — position runtime")
    table.add_column("Signal", style="bold")
    table.add_column("Valeur")
    table.add_row("Mode", report.mode)
    table.add_row("Source", report.source or "-")
    table.add_row("Lat", "-" if report.lat is None else f"{report.lat:.6f}")
    table.add_row("Lon", "-" if report.lon is None else f"{report.lon:.6f}")
    table.add_row("Failures", ", ".join(report.failures) if report.failures else "-")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("box-camera-check")
def box_camera_check(
    output: Path = typer.Option(
        Path("reports/camera-check.json"),
        help="Rapport JSON de camera runtime.",
    ),
    min_width: int = typer.Option(640, help="Largeur minimale attendue."),
    min_height: int = typer.Option(480, help="Hauteur minimale attendue."),
) -> None:
    """Verifie que la camera runtime retourne une frame exploitable."""
    config = BoxConfig.from_env()
    report = run_camera_check(
        device_index=config.camera_device,
        min_width=min_width,
        min_height=min_height,
    )
    write_camera_report(report, output)
    table = Table(title="Boring Box — camera runtime")
    table.add_column("Signal", style="bold")
    table.add_column("Valeur")
    table.add_row("Device", str(report.device_index))
    table.add_row(
        "Resolution",
        "-" if report.width is None or report.height is None else f"{report.width}x{report.height}",
    )
    table.add_row("Minimum", f"{report.min_width}x{report.min_height}")
    table.add_row("Failures", ", ".join(report.failures) if report.failures else "-")
    table.add_row("Error", report.error or "-")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("box-ready")
def box_ready(
    dataset: Path = typer.Option(Path("datasets/control_vehicle_v1"), help="Dataset YOLOv8."),
    model: Path = typer.Option(Path("models/best.pt"), help="Modele fine-tune."),
    baseline_manifest: Path = typer.Option(
        Path("datasets/baseline/manifest.jsonl"),
        help="Manifest images gratuites.",
    ),
    endpoints: Path = typer.Option(
        Path("scripts/paybyphone_endpoints.json"),
        help="JSON PayByPhone parse depuis HAR.",
    ),
    hardware_profile: Path = typer.Option(
        Path("deploy/pi/hardware-profile.json"),
        help="Profil materiel de la box installee.",
    ),
    service_unit: Path = typer.Option(
        Path("deploy/systemd/boring-box.service"),
        help="Unite systemd installee pour le service headless.",
    ),
    systemd_report: Path = typer.Option(
        Path("reports/systemd-check.json"),
        help="Rapport produit par box-systemd-check.",
    ),
    position_report: Path = typer.Option(
        Path("reports/position-check.json"),
        help="Rapport produit par box-position-check.",
    ),
    camera_report: Path = typer.Option(
        Path("reports/camera-check.json"),
        help="Rapport produit par box-camera-check.",
    ),
    vision_eval_report: Path = typer.Option(
        Path("reports/vision-eval.json"),
        help="Rapport qualite modele terrain.",
    ),
    benchmark_report: Path = typer.Option(
        Path("reports/vision-benchmark.json"),
        help="Rapport produit par vision-benchmark.",
    ),
    autopay_smoke_report: Path = typer.Option(
        Path("reports/autopay-smoke.json"),
        help="Rapport produit par autopay-smoke.",
    ),
    notification_report: Path = typer.Option(
        Path("reports/notification-test.json"),
        help="Rapport produit par box-notify-test.",
    ),
    burn_in_report: Path = typer.Option(
        Path("burn-in/report.json"),
        help="Rapport produit par box-burn-in.",
    ),
    storage_path: Path = typer.Option(
        Path("/var/lib/boring/events.jsonl"),
        help="Chemin dont la partition doit garder assez d'espace libre.",
    ),
    output: Path = typer.Option(Path("reports/box-readiness.json"), help="Rapport JSON."),
    min_burn_in_hours: float = typer.Option(10.0, help="Duree minimale du burn-in."),
    allow_dry_run: bool = typer.Option(False, help="Ne pas exiger PAYMENT_DRY_RUN=false."),
    allow_missing_autopay_smoke: bool = typer.Option(
        False,
        help="Ne pas exiger le rapport autopay-smoke.",
    ),
    allow_missing_edge_export: bool = typer.Option(
        False,
        help="Ne pas exiger best.onnx ou best.tflite.",
    ),
    allow_missing_charge_validation: bool = typer.Option(
        False,
        help="Ne pas exiger que le burn-in ait vu charge et decharge batterie.",
    ),
    allow_missing_network_recovery: bool = typer.Option(
        False,
        help="Ne pas exiger NETWORK_RECOVERY_COMMAND.",
    ),
    allow_missing_notification_webhook: bool = typer.Option(
        False,
        help="Ne pas exiger BORING_NOTIFY_WEBHOOK_URL ou NTFY_WEBHOOK_URL.",
    ),
    allow_missing_notification_test: bool = typer.Option(
        False,
        help="Ne pas exiger le rapport box-notify-test.",
    ),
    allow_missing_runtime_event_log: bool = typer.Option(
        False,
        help="Ne pas exiger le journal runtime events.jsonl.",
    ),
    allow_missing_systemd_report: bool = typer.Option(
        False,
        help="Ne pas exiger le rapport box-systemd-check.",
    ),
    allow_missing_position_report: bool = typer.Option(
        False,
        help="Ne pas exiger le rapport box-position-check.",
    ),
    allow_missing_camera_report: bool = typer.Option(
        False,
        help="Ne pas exiger le rapport box-camera-check.",
    ),
) -> None:
    """Gate final avant installation voiture / systemd."""
    report = audit_production_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=baseline_manifest,
        endpoints_path=endpoints,
        hardware_profile_path=hardware_profile,
        service_unit_path=service_unit,
        systemd_report_path=systemd_report,
        position_report_path=position_report,
        camera_report_path=camera_report,
        vision_eval_report_path=vision_eval_report,
        benchmark_report_path=benchmark_report,
        autopay_smoke_report_path=autopay_smoke_report,
        notification_report_path=notification_report,
        burn_in_report_path=burn_in_report,
        storage_path=storage_path,
        require_real_payment=not allow_dry_run,
        require_autopay_smoke=not allow_missing_autopay_smoke,
        require_edge_export=not allow_missing_edge_export,
        require_charging_seen=not allow_missing_charge_validation,
        require_network_recovery=not allow_missing_network_recovery,
        require_notification_webhook=not allow_missing_notification_webhook,
        require_notification_test=not allow_missing_notification_test,
        require_runtime_event_log=not allow_missing_runtime_event_log,
        require_systemd_report=not allow_missing_systemd_report,
        require_position_report=not allow_missing_position_report,
        require_camera_report=not allow_missing_camera_report,
        min_burn_in_hours=min_burn_in_hours,
    )
    write_production_report(report, output)
    table = Table(title="Boring Box — production readiness")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for check in report.checks:
        table.add_row(check.name, "OK" if check.ok else "FAIL", check.detail)
    table.add_row("passed", "yes" if report.passed else "no", str(output))
    console.print(table)
    raise typer.Exit(0 if report.passed else 1)


@app.command("box-evidence-pack")
def box_evidence_pack(
    output: Path = typer.Option(Path("reports/evidence-pack.json"), help="Pack JSON."),
) -> None:
    """Regroupe les rapports terrain de la box dans un pack auditable."""
    pack = build_evidence_pack(default_evidence_paths())
    write_pack(pack, output)
    table = Table(title="Boring Box — evidence pack")
    table.add_column("Evidence", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for item in pack.items:
        table.add_row(item.name, "OK" if evidence_item_ok(item) else "FAIL", item.detail)
    table.add_row("passed", "yes" if pack.passed else "no", str(output))
    console.print(table)
    raise typer.Exit(0 if pack.passed else 1)


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
    profile: str = typer.Option("positives", help="positives ou negatives."),
) -> None:
    """Scrape images gratuites depuis DuckDuckGo pour le dataset baseline."""
    project_root = Path(__file__).resolve().parents[3]
    script_path = project_root / "scripts" / "scrape_baseline.py"
    if not script_path.exists():
        console.print(f"[red]Erreur : script introuvable : {script_path}[/red]")
        raise typer.Exit(1)
    console.print(f"[bold]Scraping vers {output} ({count} images cibles)...[/bold]")
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(script_path),
            "--output",
            str(output),
            "--count",
            str(count),
            "--profile",
            profile,
        ],
        check=False,
        cwd=project_root,
    )
    if result.returncode != 0:
        console.print("[red]Le script de scraping s'est terminé avec une erreur.[/red]")
        raise typer.Exit(result.returncode)


@app.command("vision-ready")
def vision_ready(
    dataset: Path = typer.Option(
        Path("datasets/control_vehicle_v1"),
        help="Dossier YOLOv8 exporte par Roboflow.",
    ),
    model: Path = typer.Option(Path("models/best.pt"), help="Modele fine-tune attendu."),
    baseline_manifest: Path = typer.Option(
        Path("datasets/baseline/manifest.jsonl"),
        help="Manifest des images web gratuites scrapees.",
    ),
    source_catalog: Path = typer.Option(
        Path("data/vision_free_sources.json"),
        help="Catalogue JSON des sources gratuites candidates.",
    ),
    output: Path = typer.Option(Path("reports/vision-readiness.json"), help="Rapport JSON."),
    require_edge_export: bool = typer.Option(
        False,
        help="Exiger best.onnx ou best.tflite pour Pi/edge.",
    ),
    allow_unreviewed_sources: bool = typer.Option(
        False,
        help="Ne pas exiger la revue licence des images baseline.",
    ),
) -> None:
    """Audite dataset, modele et exports edge avant integration boitier."""
    report = audit_vision_readiness(
        dataset_path=dataset,
        model_path=model,
        baseline_manifest=baseline_manifest,
        source_catalog=source_catalog,
        require_edge_export=require_edge_export,
        require_license_review=not allow_unreviewed_sources,
    )
    write_vision_readiness_report(report, output)
    table = Table(title="Computer vision readiness")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for check in report.checks:
        table.add_row(check.name, "OK" if check.ok else "FAIL", check.detail)
    table.add_row("passed", "yes" if report.passed else "no", str(output))
    console.print(table)
    raise typer.Exit(0 if report.passed else 1)


@app.command("vision-sources")
def vision_sources(
    source_catalog: Path = typer.Option(
        Path("data/vision_free_sources.json"),
        help="Catalogue JSON des sources gratuites candidates.",
    ),
) -> None:
    """Affiche les sources gratuites candidates pour le dataset vision."""
    catalog = load_source_catalog(source_catalog)
    table = Table(title="Computer vision free sources")
    table.add_column("Source", style="bold")
    table.add_column("Usage")
    table.add_column("Policy")
    table.add_column("Action")
    for source in catalog.sources:
        table.add_row(
            source.name,
            ",".join(source.usage),
            source.train_policy,
            source.action,
        )
    console.print(table)


@app.command("vision-benchmark")
def vision_benchmark(
    model: Path = typer.Option(Path("models/best.pt"), help="Modele a benchmarker."),
    target: str = typer.Option("control_vehicle", help="Labels cibles, separes par virgule."),
    device: str = typer.Option("cpu", help="cpu / cuda / mps / auto."),
    camera: int = typer.Option(0, help="Index camera."),
    frames: int = typer.Option(120, help="Nombre de frames a inferer."),
    min_fps: float = typer.Option(1.0, help="FPS minimal acceptable."),
    confidence: float = typer.Option(0.5, help="Seuil de confiance."),
    output: Path = typer.Option(
        Path("reports/vision-benchmark.json"),
        help="Rapport JSON.",
    ),
) -> None:
    """Mesure le debit d'inference reel sur le hardware cible."""
    labels = tuple(label.strip() for label in target.split(",") if label.strip())
    detector = Detector(
        model_path=model,
        target_labels=labels or ("control_vehicle",),
        confidence_threshold=confidence,
        device=device,
    )
    report = run_vision_benchmark(
        detector=detector,
        frames=iter_frames(device_index=camera, fps=None),
        model_path=str(model),
        device=device,
        min_fps=min_fps,
        max_frames=frames,
    )
    write_benchmark_report(report, output)
    table = Table(title="Computer vision benchmark")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Frames", str(report.frames_processed))
    table.add_row("Detections", str(report.detections_seen))
    table.add_row("Duration", f"{report.duration_seconds:.2f}s")
    table.add_row("Measured FPS", f"{report.measured_fps:.2f}")
    table.add_row("Min FPS", f"{report.min_fps:.2f}")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("vision-eval")
def vision_eval(
    dataset: Path = typer.Option(
        Path("datasets/control_vehicle_v1"),
        help="Dossier YOLOv8 a evaluer.",
    ),
    model: Path = typer.Option(Path("models/best.pt"), help="Modele fine-tune."),
    dataset_id: str = typer.Option("field-validation-v1", help="Identifiant du set evalue."),
    split: str = typer.Option("valid", help="Split YOLO a evaluer."),
    target: str = typer.Option("control_vehicle", help="Classe cible."),
    device: str = typer.Option("cpu", help="cpu / cuda / mps / auto."),
    confidence: float = typer.Option(0.5, help="Seuil de confiance."),
    frame_interval: float = typer.Option(
        1.0,
        help="Secondes representees par chaque image extraite.",
    ),
    min_recall: float = typer.Option(0.90, help="Recall minimal acceptable."),
    max_fp_per_hour: float = typer.Option(1.0, help="Faux positifs max par heure."),
    output: Path = typer.Option(Path("reports/vision-eval.json"), help="Rapport JSON."),
) -> None:
    """Evalue le modele sur un split YOLO et produit reports/vision-eval.json."""
    detector = Detector(
        model_path=model,
        target_labels=(target,),
        confidence_threshold=confidence,
        device=device,
    )
    report = evaluate_yolo_dataset(
        detector=detector,
        dataset_path=dataset,
        model_path=str(model),
        dataset_id=dataset_id,
        split=split,
        required_class=target,
        frame_interval_seconds=frame_interval,
        min_recall=min_recall,
        max_false_positive_per_hour=max_fp_per_hour,
    )
    write_vision_eval_report(report, output)
    table = Table(title="Computer vision eval")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Frames", str(report.frames_evaluated))
    table.add_row(
        "TP / FP / FN",
        f"{report.true_positives} / {report.false_positives} / {report.false_negatives}",
    )
    table.add_row("Recall", f"{report.recall:.3f} / min {report.min_recall:.3f}")
    table.add_row("Precision", f"{report.precision:.3f}")
    table.add_row(
        "FP/hour",
        f"{report.false_positive_per_hour:.2f} / max {report.max_false_positive_per_hour:.2f}",
    )
    table.add_row("Evaluated hours", f"{report.evaluated_hours:.2f}")
    table.add_row("Invalid images", str(report.invalid_images))
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


@app.command("autopay-ready")
def autopay_ready(
    endpoints: Path = typer.Option(
        Path("scripts/paybyphone_endpoints.json"),
        help="JSON genere par parse_paybyphone_har.py.",
    ),
    output: Path = typer.Option(Path("reports/autopay-readiness.json"), help="Rapport JSON."),
    allow_dry_run: bool = typer.Option(
        False,
        help="Ne pas echouer si PAYMENT_DRY_RUN=true.",
    ),
) -> None:
    """Audite les garde-fous avant d'autoriser l'autopaiement reel."""
    report = audit_autopay_readiness(
        endpoints_path=endpoints,
        require_real_payment=not allow_dry_run,
    )
    write_autopay_report(report, output)
    table = Table(title="Autopayment readiness")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for check in report.checks:
        table.add_row(check.name, "OK" if check.ok else "FAIL", check.detail)
    table.add_row("passed", "yes" if report.passed else "no", str(output))
    console.print(table)
    raise typer.Exit(0 if report.passed else 1)


@app.command("autopay-smoke")
def autopay_smoke(
    output: Path = typer.Option(Path("reports/autopay-smoke.json"), help="Rapport JSON."),
    plate: str = typer.Option(None, envvar="DEFAULT_VEHICLE_PLATE", help="Plaque a tester."),
    duration: int = typer.Option(15, help="Duree minimale de session."),
    lat: float = typer.Option(None, envvar="BOX_LAT", help="Latitude test."),
    lon: float = typer.Option(None, envvar="BOX_LON", help="Longitude test."),
    stop_after: bool = typer.Option(True, help="Arreter la session apres verification."),
    yes: bool = typer.Option(False, "--yes", help="Confirme le paiement reel minimal."),
) -> None:
    """Demarre une session minimale reelle, verifie qu'elle est active, puis l'arrete."""
    if not yes:
        console.print("[red]Refus: ajoute --yes pour autoriser un paiement reel minimal.[/red]")
        raise typer.Exit(2)
    if plate is None or lat is None or lon is None:
        console.print("[red]Plaque, BOX_LAT et BOX_LON requis.[/red]")
        raise typer.Exit(1)
    provider = make_payment_provider()
    provider.login("", "")
    report = run_autopay_smoke(
        provider=provider,
        plate=plate,
        lat=lat,
        lon=lon,
        duration_minutes=duration,
        stop_after=stop_after,
    )
    write_autopay_smoke_report(report, output)
    table = Table(title="Autopay smoke")
    table.add_column("Signal", style="bold")
    table.add_column("Valeur")
    table.add_row("Provider", report.provider)
    table.add_row("Dry-run", "yes" if report.dry_run else "no")
    table.add_row("Zone", report.zone_id or "-")
    table.add_row("Session", report.session_id or "-")
    table.add_row("Duration", f"{report.duration_minutes} min")
    table.add_row("Position", f"{report.lat:.5f},{report.lon:.5f}")
    table.add_row("Amount", "-" if report.amount_cents is None else f"{report.amount_cents} cents")
    table.add_row("Active verified", "yes" if report.active_session_verified else "no")
    table.add_row("Stopped", "yes" if report.stopped else "no")
    table.add_row("Error", report.error or "-")
    table.add_row("Passed", "yes" if report.passed else "no")
    console.print(table)
    console.print(f"[dim]Rapport: {output}[/dim]")
    raise typer.Exit(0 if report.passed else 1)


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
            "PAYBYPHONE_RATE_OPTION_ID": hints.get("rate_option_id"),
            "PAYBYPHONE_PAYMENT_METHOD_ID": hints.get("payment_method_id"),
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
            console.print(
                "[yellow]Aucune variable à écrire (hints base_url/auth_url/client_id absents).[/yellow]"
            )

    console.print("\n[bold green]Setup PayByPhone terminé.[/bold green]")


if __name__ == "__main__":
    app()
