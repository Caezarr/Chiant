"""Tests d'intégration end-to-end de la fonction process_trigger.

On utilise un MockProvider qui implémente PaymentProvider et logue les appels
pour vérifier l'orchestration : guards (geofence, cooldown), paiement, notif.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from boring.glue import PaymentCooldown, PaymentLimits, process_trigger
from boring.payment.base import ParkingSession, PaymentProvider


@dataclass
class MockProvider(PaymentProvider):
    name: str = "mock"
    fail: bool = False
    active_session: ParkingSession | None = None
    amount_cents: int = 30
    calls: list[tuple] = field(default_factory=list)

    def login(self, username: str, password: str) -> None:
        self.calls.append(("login", username))

    def get_zone_id(self, lat: float, lon: float) -> str:
        self.calls.append(("get_zone_id", lat, lon))
        return f"MOCK-ZONE-{lat:.2f},{lon:.2f}"

    def start_session(
        self, vehicle_plate: str, location_id: str, duration_minutes: int
    ) -> ParkingSession:
        self.calls.append(("start_session", vehicle_plate, location_id, duration_minutes))
        if self.fail:
            raise RuntimeError("mock payment failed")
        now = datetime.now()
        return ParkingSession(
            provider=self.name,
            session_id=f"MOCK-{int(now.timestamp())}",
            vehicle_plate=vehicle_plate,
            location_id=location_id,
            start=now,
            end=now + timedelta(minutes=duration_minutes),
            amount_cents=self.amount_cents,
        )

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        self.calls.append(("get_active_session", vehicle_plate))
        return self.active_session

    def stop_session(self, session_id: str) -> None:
        self.calls.append(("stop_session", session_id))


class NotifyCollector:
    """Capture les notifs envoyées au lieu de les pousser à macOS."""

    def __init__(self) -> None:
        self.notifs: list[tuple] = []

    def __call__(self, title: str, message: str, sound: bool = True) -> None:
        self.notifs.append((title, message, sound))


def test_trigger_blocked_when_not_in_paid_zone():
    provider = MockProvider()
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()

    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=False,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
    )
    assert result is None
    assert provider.calls == []
    assert notif.notifs == []


def test_trigger_in_paid_zone_pays_and_notifies():
    provider = MockProvider()
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()
    successes = []

    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
        on_success=successes.append,
    )
    assert result is not None
    assert result.vehicle_plate == "AB-123-CD"
    # Provider a bien été appelé dans l'ordre
    assert provider.calls[0][0] == "get_active_session"
    assert provider.calls[1][0] == "get_zone_id"
    assert provider.calls[2][0] == "start_session"
    assert provider.calls[2][1] == "AB-123-CD"
    # Notif envoyée
    assert len(notif.notifs) == 1
    assert "payé" in notif.notifs[0][0].lower()
    assert successes == [result]


def test_cooldown_can_be_seeded_from_persisted_state():
    cooldown = PaymentCooldown(cooldown_minutes=10, last_payment=datetime.now())

    assert cooldown.allow() is False


def test_trigger_respects_cooldown():
    """Un 2e trigger dans la fenêtre cooldown n'appelle pas le paiement."""
    provider = MockProvider()
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()

    process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
    )
    n_calls_after_first = len(provider.calls)

    # Second trigger immédiat — bloqué par cooldown
    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
    )
    assert result is None
    assert len(provider.calls) == n_calls_after_first  # pas de nouvel appel
    assert len(notif.notifs) == 1  # toujours qu'une seule notif


def test_trigger_skips_when_session_already_active():
    now = datetime.now()
    provider = MockProvider(
        active_session=ParkingSession(
            provider="mock",
            session_id="ACTIVE",
            vehicle_plate="AB-123-CD",
            location_id="ZONE",
            start=now,
            end=now + timedelta(minutes=15),
            amount_cents=30,
        )
    )
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()

    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
    )

    assert result is None
    assert provider.calls == [("get_active_session", "AB-123-CD")]
    assert notif.notifs == []


def test_trigger_payment_failure_notifies_error():
    provider = MockProvider(fail=True)
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()

    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
    )
    assert result is None
    # Notif d'erreur envoyée, avec sound
    assert len(notif.notifs) == 1
    assert "échec" in notif.notifs[0][0].lower()
    assert notif.notifs[0][2] is True  # sound=True
    # Cooldown NON enregistré car le paiement a planté
    assert cooldown.last_payment is None


def test_trigger_blocks_when_daily_limit_is_already_reached():
    provider = MockProvider()
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()

    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
        payment_limits=PaymentLimits(
            max_session_amount_cents=500,
            max_daily_amount_cents=1500,
            already_paid_today_cents=1500,
        ),
    )

    assert result is None
    assert provider.calls == []
    assert "plafond" in notif.notifs[0][1].lower()


def test_trigger_stops_session_when_amount_exceeds_limit():
    provider = MockProvider(amount_cents=900)
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()
    successes = []

    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="AB-123-CD",
        duration_minutes=15,
        lat=50.6371,
        lon=3.0633,
        on_notify=notif,
        on_success=successes.append,
        payment_limits=PaymentLimits(max_session_amount_cents=500),
    )

    assert result is None
    assert provider.calls[-1][0] == "stop_session"
    assert cooldown.last_payment is None
    assert successes == []
    assert "annule" in notif.notifs[0][0].lower()


def test_trigger_failure_then_success_allowed():
    """Après un échec, on peut retenter immédiatement (cooldown pas marqué)."""
    provider = MockProvider(fail=True)
    cooldown = PaymentCooldown(cooldown_minutes=10)
    notif = NotifyCollector()

    process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="A",
        duration_minutes=15,
        lat=50.6,
        lon=3.0,
        on_notify=notif,
    )
    # Le provider se rétablit
    provider.fail = False
    result = process_trigger(
        payment=provider,
        cooldown=cooldown,
        in_paid_zone=True,
        plate="A",
        duration_minutes=15,
        lat=50.6,
        lon=3.0,
        on_notify=notif,
    )
    assert result is not None
