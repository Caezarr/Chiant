"""Client PayByPhone — STUB. Reverse engineering en Phase 5.

Endpoints à mapper via mitmproxy (cf. README) :
- POST /auth/login (OAuth2 password grant)
- GET  /locations?lat=&lon=
- POST /parking-sessions
- GET  /parking-sessions/active
- GET  /payment-methods

Référence partielle (à valider en 2026) :
https://github.com/itsff/PayByPhone-api-docs
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()


class PayByPhoneClient(PaymentProvider):
    name = "paybyphone"

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self._token: str | None = None

    def login(self, username: str, password: str) -> None:
        if self.dry_run:
            console.print(f"[yellow][DRY-RUN] login as {username or '<empty>'}[/yellow]")
            self._token = "STUB_TOKEN"
            return
        raise NotImplementedError("Phase 5: reverse PayByPhone API via mitmproxy")

    def get_zone_id(self, lat: float, lon: float) -> str:
        if self.dry_run:
            return "LILLE-STUB-ZONE"
        raise NotImplementedError("Phase 5")

    def start_session(
        self,
        vehicle_plate: str,
        location_id: str,
        duration_minutes: int,
    ) -> ParkingSession:
        if self.dry_run:
            now = datetime.now()
            session = ParkingSession(
                provider=self.name,
                session_id=f"STUB-{int(now.timestamp())}",
                vehicle_plate=vehicle_plate,
                location_id=location_id,
                start=now,
                end=now + timedelta(minutes=duration_minutes),
                amount_cents=30,
            )
            console.print(
                f"[yellow][DRY-RUN][/yellow] paiement {duration_minutes}min "
                f"plaque={vehicle_plate} zone={location_id} → {session.session_id}"
            )
            return session
        raise NotImplementedError("Phase 5")

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        if self.dry_run:
            return None
        raise NotImplementedError("Phase 5")
