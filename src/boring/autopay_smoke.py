"""Smoke test reel du provider autopaiement."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from boring.payment.base import PaymentProvider


@dataclass(frozen=True)
class AutopaySmokeReport:
    passed: bool
    provider: str
    dry_run: bool
    plate: str
    zone_id: str | None
    session_location_id: str | None
    session_id: str | None
    amount_cents: int | None
    active_session_amount_cents: int | None
    amount_verified: bool
    duration_minutes: int
    active_session_duration_minutes: int | None
    duration_verified: bool
    lat: float
    lon: float
    active_session_verified: bool
    stopped: bool
    stop_verified: bool
    tested_at: str
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def run_autopay_smoke(
    *,
    provider: PaymentProvider,
    plate: str,
    lat: float,
    lon: float,
    duration_minutes: int,
    max_session_amount_cents: int | None = None,
    stop_after: bool = True,
) -> AutopaySmokeReport:
    tested_at = datetime.now(timezone.utc).isoformat()
    dry_run = bool(getattr(provider, "dry_run", False))
    zone_id: str | None = None
    session = None
    stopped = False
    stop_verified = False
    if dry_run:
        return _report(
            provider=provider,
            dry_run=dry_run,
            plate=plate,
            duration_minutes=duration_minutes,
            lat=lat,
            lon=lon,
            tested_at=tested_at,
            error="PAYMENT_DRY_RUN must be false",
        )
    try:
        active_before = provider.get_active_session(plate)
        if active_before is not None:
            return _report(
                provider=provider,
                dry_run=dry_run,
                plate=plate,
                duration_minutes=duration_minutes,
                lat=lat,
                lon=lon,
                tested_at=tested_at,
                session_id=active_before.session_id,
                amount_cents=active_before.amount_cents,
                active_session_verified=True,
                error="active session already exists before smoke",
            )
        zone_id = provider.get_zone_id(lat, lon)
        session = provider.start_session(plate, zone_id, duration_minutes)
        active_after = provider.get_active_session(plate)
        session_location_ok = session.location_id == zone_id
        active_verified = (
            active_after is not None
            and active_after.session_id == session.session_id
            and active_after.vehicle_plate == plate
            and active_after.location_id == session.location_id
        )
        active_duration = _session_duration_minutes(active_after)
        duration_verified = active_duration == duration_minutes
        active_amount = active_after.amount_cents if active_after is not None else None
        amount_verified = active_amount == session.amount_cents
        if stop_after:
            provider.stop_session(session.session_id)
            stopped = True
            active_after_stop = provider.get_active_session(plate)
            stop_verified = active_after_stop is None
        amount_ok = session.amount_cents > 0
        max_amount_ok = (
            max_session_amount_cents is None or session.amount_cents <= max_session_amount_cents
        )
        passed = (
            amount_ok
            and max_amount_ok
            and session_location_ok
            and active_verified
            and amount_verified
            and duration_verified
            and (stopped and stop_verified if stop_after else True)
        )
        error = None
        if amount_ok and not max_amount_ok:
            error = f"session amount exceeds MAX_SESSION_AMOUNT_CENTS: {session.amount_cents}"
        elif not session_location_ok:
            error = f"session location mismatch: {session.location_id}/{zone_id}"
        elif not duration_verified:
            error = f"active session duration mismatch: {active_duration}/{duration_minutes}min"
        elif not amount_verified:
            error = f"active session amount mismatch: {active_amount}/{session.amount_cents}"
        return _report(
            provider=provider,
            dry_run=dry_run,
            plate=plate,
            duration_minutes=duration_minutes,
            lat=lat,
            lon=lon,
            tested_at=tested_at,
            zone_id=zone_id,
            session_location_id=session.location_id,
            session_id=session.session_id,
            amount_cents=session.amount_cents,
            active_session_amount_cents=active_amount,
            amount_verified=amount_verified,
            active_session_duration_minutes=active_duration,
            duration_verified=duration_verified,
            active_session_verified=active_verified,
            stopped=stopped,
            stop_verified=stop_verified,
            passed=passed,
            error=error,
        )
    except Exception as exc:
        error, stopped, stop_verified = _cleanup_after_error(
            str(exc),
            provider=provider,
            plate=plate,
            session_id=session.session_id if session is not None else None,
            stop_after=stop_after,
            stopped=stopped,
            stop_verified=stop_verified,
        )
        return _report(
            provider=provider,
            dry_run=dry_run,
            plate=plate,
            duration_minutes=duration_minutes,
            lat=lat,
            lon=lon,
            zone_id=zone_id,
            session_location_id=session.location_id if session is not None else None,
            session_id=session.session_id if session is not None else None,
            amount_cents=session.amount_cents if session is not None else None,
            stopped=stopped,
            stop_verified=stop_verified,
            tested_at=tested_at,
            error=error,
        )


def write_report(report: AutopaySmokeReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _report(
    *,
    provider: PaymentProvider,
    dry_run: bool,
    plate: str,
    duration_minutes: int,
    lat: float,
    lon: float,
    tested_at: str,
    zone_id: str | None = None,
    session_location_id: str | None = None,
    session_id: str | None = None,
    amount_cents: int | None = None,
    active_session_amount_cents: int | None = None,
    amount_verified: bool = False,
    active_session_duration_minutes: int | None = None,
    duration_verified: bool = False,
    active_session_verified: bool = False,
    stopped: bool = False,
    stop_verified: bool = False,
    passed: bool = False,
    error: str | None = None,
) -> AutopaySmokeReport:
    return AutopaySmokeReport(
        passed=passed,
        provider=provider.name,
        dry_run=dry_run,
        plate=plate,
        zone_id=zone_id,
        session_location_id=session_location_id,
        session_id=session_id,
        amount_cents=amount_cents,
        active_session_amount_cents=active_session_amount_cents,
        amount_verified=amount_verified,
        duration_minutes=duration_minutes,
        active_session_duration_minutes=active_session_duration_minutes,
        duration_verified=duration_verified,
        lat=lat,
        lon=lon,
        active_session_verified=active_session_verified,
        stopped=stopped,
        stop_verified=stop_verified,
        tested_at=tested_at,
        error=error,
    )


def _cleanup_after_error(
    error: str,
    *,
    provider: PaymentProvider,
    plate: str,
    session_id: str | None,
    stop_after: bool,
    stopped: bool,
    stop_verified: bool,
) -> tuple[str, bool, bool]:
    if session_id is None or not stop_after or stopped:
        return error, stopped, stop_verified
    try:
        provider.stop_session(session_id)
    except Exception as exc:
        return f"{error}; cleanup_stop_failed={exc}", False, False
    try:
        active_after_stop = provider.get_active_session(plate)
    except Exception as exc:
        return f"{error}; cleanup_stop_called=true; cleanup_verify_failed={exc}", True, False
    if active_after_stop is None:
        return f"{error}; cleanup_stop_verified=true", True, True
    return f"{error}; cleanup_stop_verified=false", True, False


def _session_duration_minutes(session) -> int | None:
    if session is None:
        return None
    duration_seconds = (session.end - session.start).total_seconds()
    if duration_seconds <= 0:
        return None
    return round(duration_seconds / 60)
