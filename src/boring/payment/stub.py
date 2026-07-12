"""Shared dry-run behavior for parking providers that still need reverse work."""

from __future__ import annotations

from datetime import datetime, timedelta

from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()


class DryRunParkingProvider(PaymentProvider):
    """Base class for providers whose real API integration is not implemented yet."""

    display_name: str
    stub_zone_id: str
    stub_session_prefix: str
    stub_amount_cents: int
    reverse_login_error: str
    reverse_zone_error: str

    def __init__(self, dry_run: bool = True, base_url: str = "") -> None:
        self.dry_run = dry_run
        self.base_url = base_url.rstrip("/")

    def login(self, username: str, password: str) -> None:
        if self.dry_run:
            console.print(
                f"[yellow][DRY-RUN] {self.display_name} login as {username or '<empty>'}[/yellow]"
            )
            return
        raise NotImplementedError(self.reverse_login_error)

    def get_zone_id(self, lat: float, lon: float) -> str:
        if self.dry_run:
            return self.stub_zone_id
        raise NotImplementedError(self.reverse_zone_error)

    def start_session(
        self, vehicle_plate: str, location_id: str, duration_minutes: int
    ) -> ParkingSession:
        if not self.dry_run:
            raise NotImplementedError(self.reverse_zone_error)
        now = datetime.now()
        session = ParkingSession(
            provider=self.name,
            session_id=f"{self.stub_session_prefix}{int(now.timestamp())}",
            vehicle_plate=vehicle_plate,
            location_id=location_id,
            start=now,
            end=now + timedelta(minutes=duration_minutes),
            amount_cents=self.stub_amount_cents,
        )
        console.print(
            f"[yellow][DRY-RUN][/yellow] {self.display_name} {duration_minutes}min "
            f"plaque={vehicle_plate} -> {session.session_id}"
        )
        return session

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        return None

    def stop_session(self, session_id: str) -> None:
        raise NotImplementedError(f"stop_session non implémenté pour {self.display_name}")
