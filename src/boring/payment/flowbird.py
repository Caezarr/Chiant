"""Client Flowbird / Whoosh — STUB.

Note : Flowbird a fusionné avec EasyPark fin 2024. À terme, l'API pourrait
basculer sur EasyPark — vérifier au moment du reverse. Package Android
historique : `group.flowbird.mpp`.

Reverse via HAR : https://flowbird.fr ou app mobile.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()

DEFAULT_BASE_URL = os.getenv("FLOWBIRD_API_BASE", "https://api.flowbird.com")


class FlowbirdAPIError(RuntimeError):
    pass


class FlowbirdClient(PaymentProvider):
    name = "flowbird"

    def __init__(self, dry_run: bool = True, base_url: str = DEFAULT_BASE_URL) -> None:
        self.dry_run = dry_run
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._client = httpx.Client(timeout=15.0)

    def login(self, username: str, password: str) -> None:
        if self.dry_run:
            console.print(f"[yellow][DRY-RUN] Flowbird login as {username or '<empty>'}[/yellow]")
            self._token = "STUB"
            return
        raise NotImplementedError("Flowbird reverse à faire : HAR depuis flowbird.fr")

    def get_zone_id(self, lat: float, lon: float) -> str:
        if self.dry_run:
            return "FLOWBIRD-STUB-ZONE"
        raise NotImplementedError

    def start_session(
        self, vehicle_plate: str, location_id: str, duration_minutes: int
    ) -> ParkingSession:
        if self.dry_run:
            now = datetime.now()
            session = ParkingSession(
                provider=self.name,
                session_id=f"FB-STUB-{int(now.timestamp())}",
                vehicle_plate=vehicle_plate,
                location_id=location_id,
                start=now,
                end=now + timedelta(minutes=duration_minutes),
                amount_cents=35,
            )
            console.print(
                f"[yellow][DRY-RUN][/yellow] Flowbird {duration_minutes}min "
                f"plaque={vehicle_plate} → {session.session_id}"
            )
            return session
        raise NotImplementedError

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        return None
