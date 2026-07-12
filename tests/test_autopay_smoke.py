from __future__ import annotations

from datetime import datetime, timedelta

from boring.autopay_smoke import run_autopay_smoke
from boring.payment.base import ParkingSession, PaymentProvider


class FakeProvider(PaymentProvider):
    name = "fake-pay"

    def __init__(
        self,
        *,
        dry_run: bool = False,
        active_before: bool = False,
        stop_clears_session: bool = True,
    ) -> None:
        self.dry_run = dry_run
        self.active_before = active_before
        self.stop_clears_session = stop_clears_session
        self.session: ParkingSession | None = None
        self.stopped_session_id: str | None = None

    def login(self, username: str, password: str) -> None:
        return None

    def get_zone_id(self, lat: float, lon: float) -> str:
        return "zone-1"

    def start_session(
        self,
        vehicle_plate: str,
        location_id: str,
        duration_minutes: int,
    ) -> ParkingSession:
        self.session = ParkingSession(
            provider=self.name,
            session_id="session-1",
            vehicle_plate=vehicle_plate,
            location_id=location_id,
            start=datetime(2026, 7, 9, 12, 0, 0),
            end=datetime(2026, 7, 9, 12, 0, 0) + timedelta(minutes=duration_minutes),
            amount_cents=120,
        )
        return self.session

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        if self.active_before and self.session is None:
            return ParkingSession(
                provider=self.name,
                session_id="existing-session",
                vehicle_plate=vehicle_plate,
                location_id="zone-1",
                start=datetime(2026, 7, 9, 11, 45, 0),
                end=datetime(2026, 7, 9, 12, 45, 0),
                amount_cents=200,
            )
        return self.session

    def stop_session(self, session_id: str) -> None:
        self.stopped_session_id = session_id
        if self.stop_clears_session:
            self.session = None


def test_autopay_smoke_starts_verifies_and_stops_real_session():
    provider = FakeProvider()

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is True
    assert report.dry_run is False
    assert report.zone_id == "zone-1"
    assert report.session_id == "session-1"
    assert report.amount_cents == 120
    assert report.duration_minutes == 15
    assert report.lat == 50.6371
    assert report.lon == 3.0633
    assert report.active_session_verified is True
    assert report.stopped is True
    assert report.stop_verified is True
    assert provider.stopped_session_id == "session-1"


def test_autopay_smoke_fails_when_stop_does_not_clear_active_session():
    provider = FakeProvider(stop_clears_session=False)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.stopped is True
    assert report.stop_verified is False
    assert provider.stopped_session_id == "session-1"


def test_autopay_smoke_refuses_dry_run_provider():
    provider = FakeProvider(dry_run=True)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.dry_run is True
    assert report.error == "PAYMENT_DRY_RUN must be false"
    assert provider.session is None


def test_autopay_smoke_refuses_to_start_when_session_already_exists():
    provider = FakeProvider(active_before=True)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.session_id == "existing-session"
    assert report.active_session_verified is True
    assert report.error == "active session already exists before smoke"
    assert provider.session is None
