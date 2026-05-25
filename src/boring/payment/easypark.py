"""Client EasyPark — STUB.

Doc officielle B2B : https://developer.easyparkgroup.com/
Partner API existante mais accès commercial requis. Endpoints réels à mapper
via HAR (`https://m.easypark.fr` ou `https://easypark.fr`) puis
`scripts/parse_provider_har.py easypark`.

Note : Flowbird/Whoosh a fusionné avec EasyPark fin 2024, les APIs migrent
progressivement. Vérifier au moment du reverse si EasyPark sert aussi les
zones historiquement Flowbird.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()

DEFAULT_BASE_URL = os.getenv("EASYPARK_API_BASE", "https://api.easypark.com")


class EasyParkAPIError(RuntimeError):
    pass


class EasyParkClient(PaymentProvider):
    name = "easypark"

    def __init__(self, dry_run: bool = True, base_url: str = DEFAULT_BASE_URL) -> None:
        self.dry_run = dry_run
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._client = httpx.Client(timeout=15.0)

    def login(self, username: str, password: str) -> None:
        if self.dry_run:
            console.print(f"[yellow][DRY-RUN] EasyPark login as {username or '<empty>'}[/yellow]")
            self._token = "STUB"
            return
        raise NotImplementedError("EasyPark reverse à faire : HAR depuis m.easypark.fr")

    def get_zone_id(self, lat: float, lon: float) -> str:
        if self.dry_run:
            return "EASYPARK-STUB-ZONE"
        raise NotImplementedError

    def start_session(
        self, vehicle_plate: str, location_id: str, duration_minutes: int
    ) -> ParkingSession:
        if self.dry_run:
            now = datetime.now()
            session = ParkingSession(
                provider=self.name,
                session_id=f"EP-STUB-{int(now.timestamp())}",
                vehicle_plate=vehicle_plate,
                location_id=location_id,
                start=now,
                end=now + timedelta(minutes=duration_minutes),
                amount_cents=35,
            )
            console.print(
                f"[yellow][DRY-RUN][/yellow] EasyPark {duration_minutes}min "
                f"plaque={vehicle_plate} → {session.session_id}"
            )
            return session
        raise NotImplementedError

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        return None
