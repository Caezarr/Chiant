"""Etat persistant local de la box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from boring.payment.base import ParkingSession


@dataclass
class BoxState:
    last_payment_at: datetime | None = None
    last_session_id: str | None = None
    last_session_provider: str | None = None
    last_session_plate: str | None = None
    daily_paid_on: date | None = None
    daily_paid_cents: int = 0
    load_error: str | None = None


class BoxStateStore:
    """Stocke l'etat minimal pour survivre a un reboot systemd."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> BoxState:
        if not self.path.exists():
            return BoxState()
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return BoxState(load_error=f"invalid state file: {exc}")
        try:
            return BoxState(
                last_payment_at=_parse_dt(data.get("last_payment_at")),
                last_session_id=data.get("last_session_id"),
                last_session_provider=data.get("last_session_provider"),
                last_session_plate=data.get("last_session_plate"),
                daily_paid_on=_parse_date(data.get("daily_paid_on")),
                daily_paid_cents=int(data.get("daily_paid_cents") or 0),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            return BoxState(load_error=f"invalid state payload: {exc}")

    def save(self, state: BoxState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(state)
        payload.pop("load_error", None)
        if state.last_payment_at is not None:
            payload["last_payment_at"] = state.last_payment_at.isoformat()
        if state.daily_paid_on is not None:
            payload["daily_paid_on"] = state.daily_paid_on.isoformat()
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def record_session(self, session: ParkingSession) -> None:
        current = self.load()
        if current.load_error is not None:
            raise RuntimeError(current.load_error)
        payment_day = session.start.date()
        previous_total = current.daily_paid_cents if current.daily_paid_on == payment_day else 0
        self.save(
            BoxState(
                last_payment_at=session.start,
                last_session_id=session.session_id,
                last_session_provider=session.provider,
                last_session_plate=session.vehicle_plate,
                daily_paid_on=payment_day,
                daily_paid_cents=previous_total + max(0, session.amount_cents),
            )
        )

    def paid_today_cents(self, today: date | None = None) -> int:
        state = self.load()
        if state.load_error is not None:
            raise RuntimeError(state.load_error)
        today = today or datetime.now().date()
        if state.daily_paid_on != today:
            return 0
        return state.daily_paid_cents


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
