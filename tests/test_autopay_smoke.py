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
        amount_cents: int = 120,
        active_amount_cents: int | None = None,
        fail_active_after_start: bool = False,
        session_location_id: str = "zone-1",
        active_duration_minutes: int | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.active_before = active_before
        self.stop_clears_session = stop_clears_session
        self.amount_cents = amount_cents
        self.active_amount_cents = active_amount_cents
        self.fail_active_after_start = fail_active_after_start
        self.session_location_id = session_location_id
        self.active_duration_minutes = active_duration_minutes
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
            location_id=self.session_location_id,
            start=datetime(2026, 7, 9, 12, 0, 0),
            end=datetime(2026, 7, 9, 12, 0, 0)
            + timedelta(minutes=self.active_duration_minutes or duration_minutes),
            amount_cents=self.amount_cents,
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
        if self.fail_active_after_start and self.session is not None:
            raise RuntimeError("active session lookup failed")
        if self.session is None or self.active_amount_cents is None:
            return self.session
        return ParkingSession(
            provider=self.session.provider,
            session_id=self.session.session_id,
            vehicle_plate=self.session.vehicle_plate,
            location_id=self.session.location_id,
            start=self.session.start,
            end=self.session.end,
            amount_cents=self.active_amount_cents,
        )

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
    assert report.session_location_id == "zone-1"
    assert report.session_id == "session-1"
    assert report.amount_cents == 120
    assert report.active_session_amount_cents == 120
    assert report.amount_verified is True
    assert report.duration_minutes == 15
    assert report.active_session_duration_minutes == 15
    assert report.duration_verified is True
    assert report.lat == 50.6371
    assert report.lon == 3.0633
    assert report.active_session_verified is True
    assert report.stopped is True
    assert report.stop_verified is True
    assert provider.stopped_session_id == "session-1"


def test_autopay_smoke_fails_when_active_session_duration_differs():
    provider = FakeProvider(active_duration_minutes=5)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.active_session_duration_minutes == 5
    assert report.duration_verified is False
    assert "duration mismatch" in str(report.error)
    assert provider.stopped_session_id == "session-1"


def test_autopay_smoke_fails_when_session_uses_other_zone():
    provider = FakeProvider(session_location_id="zone-other")

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.zone_id == "zone-1"
    assert report.session_location_id == "zone-other"
    assert "session location mismatch" in str(report.error)
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


def test_autopay_smoke_stops_started_session_when_verification_crashes():
    provider = FakeProvider(fail_active_after_start=True)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.session_id == "session-1"
    assert report.amount_cents == 120
    assert report.stopped is True
    assert report.stop_verified is True
    assert "active session lookup failed" in str(report.error)
    assert "cleanup_stop_verified=true" in str(report.error)
    assert provider.stopped_session_id == "session-1"
    assert provider.session is None


def test_autopay_smoke_fails_when_amount_exceeds_limit():
    provider = FakeProvider(amount_cents=800)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
        max_session_amount_cents=500,
    )

    assert report.passed is False
    assert report.amount_cents == 800
    assert report.stopped is True
    assert report.stop_verified is True
    assert "exceeds MAX_SESSION_AMOUNT_CENTS" in str(report.error)
    assert provider.stopped_session_id == "session-1"


def test_autopay_smoke_fails_when_active_session_amount_differs():
    provider = FakeProvider(amount_cents=120, active_amount_cents=180)

    report = run_autopay_smoke(
        provider=provider,
        plate="AB-123-CD",
        lat=50.6371,
        lon=3.0633,
        duration_minutes=15,
    )

    assert report.passed is False
    assert report.amount_cents == 120
    assert report.active_session_amount_cents == 180
    assert report.amount_verified is False
    assert "active session amount mismatch" in str(report.error)
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
