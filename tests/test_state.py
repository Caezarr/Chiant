from __future__ import annotations

from datetime import date, datetime, timedelta

from boring.payment.base import ParkingSession
from boring.state import BoxState, BoxStateStore


def test_state_store_missing_file_loads_empty(tmp_path):
    store = BoxStateStore(tmp_path / "state.json")

    state = store.load()

    assert state.last_payment_at is None
    assert state.last_session_id is None
    assert state.load_error is None


def test_state_store_corrupt_file_reports_load_error(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not-json")
    store = BoxStateStore(path)

    state = store.load()

    assert state.load_error is not None
    assert "invalid state file" in state.load_error


def test_state_store_refuses_daily_total_when_state_is_corrupt(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not-json")
    store = BoxStateStore(path)

    try:
        store.paid_today_cents(date(2026, 7, 9))
    except RuntimeError as exc:
        assert "invalid state file" in str(exc)
    else:
        raise AssertionError("expected corrupt state to block paid_today_cents")


def test_state_store_roundtrip(tmp_path):
    store = BoxStateStore(tmp_path / "state.json")
    now = datetime.now()

    store.save(BoxState(last_payment_at=now, last_session_id="S1"))
    loaded = store.load()

    assert loaded.last_payment_at == now
    assert loaded.last_session_id == "S1"


def test_state_store_record_session(tmp_path):
    store = BoxStateStore(tmp_path / "state.json")
    now = datetime.now()
    session = ParkingSession(
        provider="mock",
        session_id="S1",
        vehicle_plate="AB-123-CD",
        location_id="ZONE",
        start=now,
        end=now + timedelta(minutes=15),
        amount_cents=30,
    )

    store.record_session(session)
    loaded = store.load()

    assert loaded.last_payment_at == now
    assert loaded.last_session_id == "S1"
    assert loaded.last_session_provider == "mock"
    assert loaded.last_session_plate == "AB-123-CD"
    assert loaded.daily_paid_on == now.date()
    assert loaded.daily_paid_cents == 30


def test_state_store_tracks_daily_paid_total(tmp_path):
    store = BoxStateStore(tmp_path / "state.json")
    first = datetime(2026, 7, 9, 9, 0)
    second = datetime(2026, 7, 9, 10, 0)
    next_day = datetime(2026, 7, 10, 9, 0)

    store.record_session(_session("S1", first, 300))
    store.record_session(_session("S2", second, 400))

    assert store.paid_today_cents(date(2026, 7, 9)) == 700
    assert store.paid_today_cents(date(2026, 7, 10)) == 0

    store.record_session(_session("S3", next_day, 500))

    assert store.paid_today_cents(date(2026, 7, 9)) == 0
    assert store.paid_today_cents(date(2026, 7, 10)) == 500


def _session(session_id: str, start: datetime, amount_cents: int) -> ParkingSession:
    return ParkingSession(
        provider="mock",
        session_id=session_id,
        vehicle_plate="AB-123-CD",
        location_id="ZONE",
        start=start,
        end=start + timedelta(minutes=15),
        amount_cents=amount_cents,
    )
