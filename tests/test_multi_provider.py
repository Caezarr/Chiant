"""Tests du registry multi-provider et des stubs."""

from __future__ import annotations

import pytest

from boring.payment import PROVIDER_REGISTRY, get_provider_class
from boring.payment.base import PaymentProvider
from boring.payment.easypark import EasyParkClient
from boring.payment.flowbird import FlowbirdClient
from boring.payment.opngo import OPnGOClient
from boring.payment.paybyphone import PayByPhoneClient


def test_registry_contains_all_providers():
    expected = {"paybyphone", "paybyphone-assisted", "easypark", "flowbird", "opngo"}
    assert set(PROVIDER_REGISTRY) == expected


def test_get_provider_class_known():
    assert get_provider_class("paybyphone") is PayByPhoneClient
    assert get_provider_class("easypark") is EasyParkClient
    assert get_provider_class("flowbird") is FlowbirdClient
    assert get_provider_class("opngo") is OPnGOClient


def test_get_provider_class_case_insensitive():
    assert get_provider_class("PayByPhone") is PayByPhoneClient
    assert get_provider_class("  EasyPark ") is EasyParkClient


def test_get_provider_class_unknown_raises():
    with pytest.raises(KeyError):
        get_provider_class("ghost-provider")


@pytest.mark.parametrize(
    "provider_cls",
    [PayByPhoneClient, EasyParkClient, FlowbirdClient, OPnGOClient],
)
def test_provider_dry_run_session_lifecycle(provider_cls):
    p = provider_cls(dry_run=True)
    assert isinstance(p, PaymentProvider)
    p.login("user", "pwd")
    zone = p.get_zone_id(50.6371, 3.0633)
    assert isinstance(zone, str)
    session = p.start_session("AB-123-CD", zone, 15)
    assert session.provider == p.name
    assert session.vehicle_plate == "AB-123-CD"
    assert (session.end - session.start).total_seconds() == 15 * 60


@pytest.mark.parametrize(
    "provider_cls,prefix",
    [
        (PayByPhoneClient, "STUB-"),
        (EasyParkClient, "EP-STUB-"),
        (FlowbirdClient, "FB-STUB-"),
        (OPnGOClient, "OP-STUB-"),
    ],
)
def test_provider_session_id_prefix(provider_cls, prefix):
    """Chaque provider a un préfixe distinct pour son session_id stub."""
    p = provider_cls(dry_run=True)
    p.login("", "")
    session = p.start_session("X", "Z", 5)
    assert session.session_id.startswith(prefix)
