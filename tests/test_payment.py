"""Tests des providers de paiement."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from boring.payment.assisted import AssistedPayByPhone, build_deep_link
from boring.payment.base import PaymentProvider
from boring.payment.paybyphone import PayByPhoneAPIError, PayByPhoneClient, _AuthToken


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


def test_paybyphone_real_payload_includes_har_hints(monkeypatch):
    monkeypatch.setenv("PAYBYPHONE_RATE_OPTION_ID", "RATE-1")
    monkeypatch.setenv("PAYBYPHONE_PAYMENT_METHOD_ID", "PM-1")
    client = PayByPhoneClient(dry_run=False)
    client._token = _AuthToken("TOKEN", None, datetime.now() + timedelta(hours=1))
    client._account_id = "ACCOUNT-1"
    fake = _FakeHttpClient()
    client._client = fake

    session = client.start_session("AB-123-CD", "LILLE-1", 15)

    assert session.session_id == "SESSION-1"
    assert fake.payload["locationId"] == "LILLE-1"
    assert fake.payload["licensePlate"] == "AB-123-CD"
    assert fake.payload["rateOptionId"] == "RATE-1"
    assert fake.payload["paymentMethodId"] == "PM-1"


def test_paybyphone_location_lookup_returns_single_zone(monkeypatch):
    monkeypatch.delenv("PAYBYPHONE_LOCATION_ID", raising=False)
    client = _logged_in_client()
    fake = _FakeHttpClient(locations=[{"locationId": "LILLE-1"}])
    client._client = fake

    assert client.get_zone_id(50.6371, 3.0633) == "LILLE-1"


def test_paybyphone_location_lookup_refuses_ambiguous_zones(monkeypatch):
    monkeypatch.delenv("PAYBYPHONE_LOCATION_ID", raising=False)
    client = _logged_in_client()
    client._client = _FakeHttpClient(
        locations=[{"locationId": "LILLE-1"}, {"locationId": "LILLE-2"}]
    )

    try:
        client.get_zone_id(50.6371, 3.0633)
    except PayByPhoneAPIError as exc:
        assert "ambigue" in str(exc)
        assert "PAYBYPHONE_LOCATION_ID" in str(exc)
    else:
        raise AssertionError("ambiguous location lookup should fail")


def test_paybyphone_location_lookup_uses_explicit_override(monkeypatch):
    monkeypatch.setenv("PAYBYPHONE_LOCATION_ID", "LILLE-FIXED")
    client = _logged_in_client()
    fake = _FakeHttpClient(locations=[{"locationId": "LILLE-1"}, {"locationId": "LILLE-2"}])
    client._client = fake

    assert client.get_zone_id(50.6371, 3.0633) == "LILLE-FIXED"
    assert fake.get_calls == []


def _logged_in_client() -> PayByPhoneClient:
    client = PayByPhoneClient(dry_run=False)
    client._token = _AuthToken("TOKEN", None, datetime.now() + timedelta(hours=1))
    client._account_id = "ACCOUNT-1"
    return client


class _FakeResponse:
    def __init__(self, payload: dict | list | None = None) -> None:
        self.payload = payload or {"sessionId": "SESSION-1", "totalCost": {"amount": 0.3}}
        self.content = b"{}"
        self.headers = {}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class _FakeHttpClient:
    def __init__(self, locations: list[dict] | None = None) -> None:
        self.payload = {}
        self.locations = locations or []
        self.get_calls = []

    def post(self, url: str, json: dict) -> _FakeResponse:
        self.url = url
        self.payload = json
        return _FakeResponse()

    def get(self, url: str, params: dict | None = None) -> _FakeResponse:
        self.get_calls.append((url, params))
        return _FakeResponse(self.locations)
