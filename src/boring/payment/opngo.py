"""Client OPnGO / Indigo Neo — STUB.

Groupe Indigo. Renommée Indigo Neo en 2023.

OPnGO a historiquement exposé une API publique : https://developer.opngo.com/
(à vérifier post-rebrand). Si toujours actif, c'est la seule API parking FR
avec un tier gratuit utilisable directement sans accord commercial — à privilégier
en priorité pour Boring.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()

DEFAULT_BASE_URL = os.getenv("OPNGO_API_BASE", "https://api.opngo.com")


class OPnGOAPIError(RuntimeError):
    pass


class OPnGOClient(PaymentProvider):
    name = "opngo"

    def __init__(self, dry_run: bool = True, base_url: str = DEFAULT_BASE_URL) -> None:
        self.dry_run = dry_run
        self.base_url = base_url.rstrip("/")
        self._api_key = os.getenv("OPNGO_API_KEY")
        self._client = httpx.Client(timeout=15.0)

    def login(self, username: str, password: str) -> None:
        # OPnGO utilise probablement un API key plutôt que user/pass — set via env
        if self.dry_run:
            console.print("[yellow][DRY-RUN] OPnGO via API key[/yellow]")
            return
        if not self._api_key:
            raise OPnGOAPIError("OPNGO_API_KEY non défini dans .env")
        self._client.headers["X-API-Key"] = self._api_key

    def get_zone_id(self, lat: float, lon: float) -> str:
        if self.dry_run:
            return "OPNGO-STUB-ZONE"
        raise NotImplementedError("À implémenter une fois doc OPnGO développeur validée")

    def start_session(
        self, vehicle_plate: str, location_id: str, duration_minutes: int
    ) -> ParkingSession:
        if self.dry_run:
            now = datetime.now()
            session = ParkingSession(
                provider=self.name,
                session_id=f"OP-STUB-{int(now.timestamp())}",
                vehicle_plate=vehicle_plate,
                location_id=location_id,
                start=now,
                end=now + timedelta(minutes=duration_minutes),
                amount_cents=30,
            )
            console.print(
                f"[yellow][DRY-RUN][/yellow] OPnGO {duration_minutes}min "
                f"plaque={vehicle_plate} → {session.session_id}"
            )
            return session
        raise NotImplementedError

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        return None

    def stop_session(self, session_id: str) -> None:
        raise NotImplementedError("stop_session non implémenté pour ce provider")
