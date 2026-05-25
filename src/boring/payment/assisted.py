"""Provider de paiement assisté : envoie un rappel iMessage contextualisé à l'iPhone.

Pipeline :
1. La détection émet un événement
2. Ce provider envoie un iMessage à l'iPhone de l'utilisateur (osascript Messages.app)
   avec : plaque, durée recommandée, lien d'ouverture de l'app PayByPhone
3. L'utilisateur tape sur le lien → l'app s'ouvre, il saisit/valide manuellement

⚠️ Note importante : les apps PayByPhone, EasyPark, Flowbird, OPnGO n'exposent
**pas** d'URL scheme tiers stable permettant de pré-remplir les champs.
Le deep link `paybyphone://` ou Universal Link `https://m.paybyphone.fr/`
ne fait qu'ouvrir l'app (pas de pré-remplissage). Pour un pré-remplissage
ou un paiement automatique, voir `boring.payment.paybyphone.PayByPhoneClient`
(mode `dry_run=False` après reverse via HAR).

Mode assisted = rappel intelligent légalement défendable, V1 shippable
immédiatement. Mode auto API = paiement réel, dispo après Phase 5.
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

# Liens candidats — testés dans l'ordre. Universal Link en premier (iOS ouvre l'app
# si installée, sinon ouvre Safari), URL scheme custom en fallback (peut lancer
# l'app si elle est listée dans LSApplicationQueriesSchemes du système).
# Aucun ne supporte le pré-remplissage des champs (cf. veille URL scheme).
DEEP_LINK_CANDIDATES = [
    "https://m.paybyphone.fr/",  # Universal Link (recommandé)
    "paybyphone://",  # URL scheme custom, fallback
]

DEFAULT_WEB_URL = "https://m.paybyphone.fr/"


def build_deep_link(
    location_id: str,
    duration_minutes: int,
    vehicle_plate: str,
    scheme: str | None = None,
) -> str:
    """Construit l'URL d'ouverture de l'app.

    Les params sont passés à titre informatif (UTM-like, certains brokers
    de deep link les conservent) mais l'app PayByPhone ne pré-remplit pas
    les champs à partir d'eux.
    """
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
            f"🅿️ Boring — contrôle automatisé détecté à proximité.\n"
            f"Pense à payer ta session : {duration_minutes} min sur plaque {vehicle_plate}.\n"
            f"Ouvrir l'app → {url}"
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
