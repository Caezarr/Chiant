"""Orchestration end-to-end : détection → décision → paiement → notif."""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from rich.console import Console

from boring.detect import Detector, StreamTracker, run_live_detection
from boring.geofence import LilleParkingZones
from boring.notify import notify
from boring.payment import get_provider_class
from boring.payment.assisted import AssistedPayByPhone
from boring.payment.base import ParkingSession, PaymentProvider


def make_payment_provider() -> PaymentProvider:
    """Construit le provider de paiement selon les variables d'env.

    Logique :
    - Si PAYMENT_MODE=assisted (défaut) → AssistedPayByPhone (iMessage).
    - Si PAYMENT_MODE=auto → utilise PAYMENT_PROVIDER (défaut: paybyphone)
      pour choisir le client API (paybyphone, easypark, flowbird, opngo).
    """
    mode = os.getenv("PAYMENT_MODE", "assisted").lower()
    if mode == "assisted":
        return AssistedPayByPhone(recipient_phone=os.getenv("ASSISTED_IMESSAGE_RECIPIENT") or None)
    provider_name = os.getenv("PAYMENT_PROVIDER", "paybyphone").lower()
    provider_cls = get_provider_class(provider_name)
    return provider_cls(dry_run=True)


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

    payment = make_payment_provider()
    payment.login(
        os.getenv("PAYBYPHONE_USERNAME", ""),
        os.getenv("PAYBYPHONE_PASSWORD", ""),
    )
    console.print(f"[dim]Provider paiement actif : {payment.name}[/dim]")

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
        console.print(f"[red bold]⚡ TRIGGER[/red bold] — {len(detections)} véhicule(s)")
        process_trigger(
            payment=payment,
            cooldown=cooldown,
            in_paid_zone=in_paid_zone,
            plate=plate,
            duration_minutes=duration,
            lat=current_lat or 50.6292,
            lon=current_lon or 3.0573,
        )


def process_trigger(
    *,
    payment: PaymentProvider,
    cooldown: PaymentCooldown,
    in_paid_zone: bool,
    plate: str,
    duration_minutes: int,
    lat: float,
    lon: float,
    on_notify=notify,
) -> ParkingSession | None:
    """Traite un événement trigger : check guards → paiement → notif.

    Retourne la session créée, ou None si bloquée (hors zone, cooldown, échec).
    Le hook `on_notify` est injecté pour faciliter les tests.
    """
    if not in_paid_zone:
        return None
    if not cooldown.allow():
        return None
    try:
        zone_id = payment.get_zone_id(lat, lon)
        session = payment.start_session(plate, zone_id, duration_minutes)
        cooldown.record()
        on_notify(
            "Boring — stationnement payé",
            f"{duration_minutes} min sur plaque {plate}. Session {session.session_id}.",
        )
        return session
    except Exception as e:
        on_notify("Boring — échec paiement", str(e), sound=True)
        return None
