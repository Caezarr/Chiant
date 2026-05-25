"""Orchestration end-to-end : détection → décision → paiement → notif."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from rich.console import Console

from boring.detect import Detector, StreamTracker, run_live_detection
from boring.geofence import LilleParkingZones
from boring.notify import notify
from boring.payment.paybyphone import PayByPhoneClient

load_dotenv()
console = Console()


class PaymentCooldown:
    """Empêche les paiements en doublon dans une fenêtre temporelle."""

    def __init__(self, cooldown_minutes: int = 10) -> None:
        self.cooldown = timedelta(minutes=cooldown_minutes)
        self.last_payment: datetime | None = None

    def allow(self) -> bool:
        if self.last_payment is None:
            return True
        return datetime.now() - self.last_payment > self.cooldown

    def record(self) -> None:
        self.last_payment = datetime.now()


def run_pipeline(
    current_lat: float | None = None,
    current_lon: float | None = None,
    fps: float = 5.0,
) -> None:
    """Boucle complète. Lat/lon : position connue de la voiture (override géoloc)."""
    conf = float(os.getenv("DETECTION_CONFIDENCE_THRESHOLD", "0.5"))
    consecutive = int(os.getenv("DETECTION_CONSECUTIVE_FRAMES", "3"))
    duration = int(os.getenv("DEFAULT_DURATION_MINUTES", "15"))
    cooldown_min = int(os.getenv("COOLDOWN_MINUTES", "10"))
    plate = os.getenv("DEFAULT_VEHICLE_PLATE", "AA-000-AA")

    detector = Detector(confidence_threshold=conf)
    tracker = StreamTracker(required_consecutive=consecutive)
    cooldown = PaymentCooldown(cooldown_minutes=cooldown_min)

    payment = PayByPhoneClient(dry_run=True)  # passera à False après reverse Phase 5
    payment.login(
        os.getenv("PAYBYPHONE_USERNAME", ""),
        os.getenv("PAYBYPHONE_PASSWORD", ""),
    )

    in_paid_zone = True
    if current_lat is not None and current_lon is not None:
        try:
            zones = LilleParkingZones()
            in_paid_zone = zones.is_in_paid_zone(current_lat, current_lon)
            console.print(
                f"Position ({current_lat:.4f}, {current_lon:.4f}) en zone payante : {in_paid_zone}"
            )
        except FileNotFoundError as e:
            console.print(f"[yellow]{e}[/yellow] Geofence désactivée.")

    if not in_paid_zone:
        console.print("[yellow]Hors zone payante — preview seul.[/yellow]")

    console.print("[bold green]Pipeline Boring lancé.[/bold green] Ctrl+C pour stopper.")

    for detections in run_live_detection(detector=detector, fps=fps, tracker=tracker):
        if not in_paid_zone:
            continue
        if not cooldown.allow():
            console.print("[dim]Détection ignorée (cooldown actif).[/dim]")
            continue

        console.print(f"[red bold]⚡ TRIGGER[/red bold] — {len(detections)} véhicule(s)")
        try:
            zone_id = payment.get_zone_id(current_lat or 50.6292, current_lon or 3.0573)
            session = payment.start_session(plate, zone_id, duration)
            cooldown.record()
            notify(
                "Boring — stationnement payé",
                f"{duration} min sur plaque {plate}. Session {session.session_id}.",
            )
        except Exception as e:
            console.print(f"[red]Échec paiement : {e}[/red]")
            notify("Boring — échec paiement", str(e), sound=True)
