"""Provider de paiement assisté : la détection construit la requête, l'utilisateur valide.

Pipeline :
1. La détection émet un événement
2. Ce provider construit un deep link (URL scheme PayByPhone si dispo, fallback web)
3. Le lien est envoyé à l'iPhone de l'utilisateur via iMessage (osascript)
4. L'utilisateur tape sur le lien : l'app s'ouvre pré-remplie, il valide en 1 tap

Architecture défendable juridiquement : l'utilisateur reste décisionnaire final,
le système est un "assistant de paiement optimisé", pas un automate de paiement.

Latence end-to-end visée : < 4 secondes (détection → confirmation user).
"""

from __future__ import annotations

import os
import shlex
import subprocess
from datetime import datetime, timedelta
from urllib.parse import urlencode

from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()

# Schemas candidats — à raffiner après veille URL scheme.
# Le 1er qui marche sur iOS est utilisé ; sinon fallback web.
DEEP_LINK_CANDIDATES = [
    "paybyphone://start-parking",  # hypothèse : à valider via décompilation APK
    "pbp://start-parking",
    "https://m.paybyphone.fr/parking/start",  # fallback web
]

DEFAULT_WEB_URL = "https://m.paybyphone.fr/"


def build_deep_link(
    location_id: str,
    duration_minutes: int,
    vehicle_plate: str,
    scheme: str | None = None,
) -> str:
    """Construit l'URL de paiement avec les paramètres pré-remplis."""
    base = scheme or DEEP_LINK_CANDIDATES[0]
    params = urlencode(
        {
            "location": location_id,
            "duration": duration_minutes,
            "plate": vehicle_plate,
            "source": "boring",
        }
    )
    return f"{base}?{params}"


def send_imessage(recipient: str, body: str) -> None:
    """Envoie un iMessage via Messages.app (osascript)."""
    script = f"""
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant {shlex.quote(recipient)} of targetService
        send {shlex.quote(body)} to targetBuddy
    end tell
    """
    subprocess.run(["osascript", "-e", script], check=False)


class AssistedPayByPhone(PaymentProvider):
    """Mode 'assisted' : compose la requête, l'envoie via iMessage à l'iPhone user.

    L'utilisateur reçoit une notification iMessage avec un lien tappable qui
    ouvre l'app PayByPhone pré-remplie. Il valide en 1 tap.
    """

    name = "paybyphone-assisted"

    def __init__(
        self,
        recipient_phone: str | None = None,
        deep_link_scheme: str | None = None,
    ) -> None:
        self.recipient_phone = recipient_phone or os.getenv("ASSISTED_IMESSAGE_RECIPIENT", "")
        self.deep_link_scheme = deep_link_scheme

    def login(self, username: str, password: str) -> None:
        # Pas de login : c'est l'app native qui gère l'auth.
        if not self.recipient_phone:
            console.print(
                "[yellow]⚠ ASSISTED_IMESSAGE_RECIPIENT non défini dans .env "
                "— les iMessages ne seront pas envoyés.[/yellow]"
            )

    def get_zone_id(self, lat: float, lon: float) -> str:
        # En mode assisted, la zone est résolue par l'app native après réception
        # du deep link. On passe une zone "auto" / les coords brutes.
        return f"auto:{lat:.5f},{lon:.5f}"

    def start_session(
        self,
        vehicle_plate: str,
        location_id: str,
        duration_minutes: int,
    ) -> ParkingSession:
        url = build_deep_link(
            location_id=location_id,
            duration_minutes=duration_minutes,
            vehicle_plate=vehicle_plate,
            scheme=self.deep_link_scheme,
        )
        body = (
            f"🅿️ Stationnement à valider : {duration_minutes} min sur plaque {vehicle_plate}.\n"
            f"Tap → {url}"
        )
        now = datetime.now()
        if self.recipient_phone:
            try:
                send_imessage(self.recipient_phone, body)
                console.print(
                    f"[green]✓[/green] iMessage envoyé à {self.recipient_phone[-4:].rjust(len(self.recipient_phone), '•')}"
                )
            except Exception as e:
                console.print(f"[red]Échec iMessage : {e}[/red]")
        else:
            console.print(f"[yellow][DRY-RUN][/yellow] iMessage non envoyé. URL : {url}")

        return ParkingSession(
            provider=self.name,
            session_id=f"ASSISTED-{int(now.timestamp())}",
            vehicle_plate=vehicle_plate,
            location_id=location_id,
            start=now,
            end=now + timedelta(minutes=duration_minutes),
            amount_cents=0,  # le montant réel sera celui appliqué par l'app PayByPhone après tap user
        )

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        # En mode assisted, on n'a pas de visibilité sur l'état réel — c'est l'app PayByPhone qui le détient.
        return None
