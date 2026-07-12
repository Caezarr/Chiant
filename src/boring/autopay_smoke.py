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
    session_id: str | None
    amount_cents: int | None
    duration_minutes: int
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
    stop_after: bool = True,
) -> AutopaySmokeReport:
    tested_at = datetime.now(timezone.utc).isoformat()
    dry_run = bool(getattr(provider, "dry_run", False))
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
        active_verified = active_after is not None and active_after.session_id == session.session_id
        stopped = False
        stop_verified = False
        if stop_after:
            provider.stop_session(session.session_id)
            stopped = True
            active_after_stop = provider.get_active_session(plate)
            stop_verified = active_after_stop is None
        passed = (
            session.amount_cents > 0
            and active_verified
            and (stopped and stop_verified if stop_after else True)
        )
        return _report(
            provider=provider,
            dry_run=dry_run,
            plate=plate,
            duration_minutes=duration_minutes,
            lat=lat,
            lon=lon,
            tested_at=tested_at,
            zone_id=zone_id,
            session_id=session.session_id,
            amount_cents=session.amount_cents,
            active_session_verified=active_verified,
            stopped=stopped,
            stop_verified=stop_verified,
            passed=passed,
        )
    except Exception as exc:
        return _report(
            provider=provider,
            dry_run=dry_run,
            plate=plate,
            duration_minutes=duration_minutes,
            lat=lat,
            lon=lon,
            tested_at=tested_at,
            error=str(exc),
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
    session_id: str | None = None,
    amount_cents: int | None = None,
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
        session_id=session_id,
        amount_cents=amount_cents,
        duration_minutes=duration_minutes,
        lat=lat,
        lon=lon,
        active_session_verified=active_session_verified,
        stopped=stopped,
        stop_verified=stop_verified,
        tested_at=tested_at,
        error=error,
    )
