"""Tests des providers de paiement."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from boring.payment.assisted import AssistedPayByPhone, build_deep_link
from boring.payment.base import PaymentProvider
from boring.payment.paybyphone import PayByPhoneClient


def test_deep_link_contains_required_params():
    url = build_deep_link("LILLE-Z12", 15, "AB-123-CD")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert params["location"] == ["LILLE-Z12"]
    assert params["duration"] == ["15"]
    assert params["plate"] == ["AB-123-CD"]
    assert params["source"] == ["boring"]


def test_deep_link_custom_scheme():
    url = build_deep_link("X", 5, "Y", scheme="https://example.com/pay")
    assert url.startswith("https://example.com/pay?")


def test_assisted_implements_provider_interface():
    p = AssistedPayByPhone()
    assert isinstance(p, PaymentProvider)
    assert p.name == "paybyphone-assisted"


def test_assisted_creates_session_in_dry_run():
    """Sans recipient phone configuré, ne plante pas et crée quand même la session."""
    p = AssistedPayByPhone(recipient_phone="")
    p.login("", "")
    session = p.start_session("AB-123-CD", "LILLE-Z12", 15)
    assert session.provider == "paybyphone-assisted"
    assert session.vehicle_plate == "AB-123-CD"
    assert (session.end - session.start).total_seconds() == 15 * 60


def test_paybyphone_stub_session():
    """Le stub PayByPhone produit une session ParkingSession valide en dry_run."""
    p = PayByPhoneClient(dry_run=True)
    p.login("user", "pwd")
    s = p.start_session("AB-123-CD", "Z1", 15)
    assert s.session_id.startswith("STUB-")
    assert s.amount_cents == 30
