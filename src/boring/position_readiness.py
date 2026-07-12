"""Runtime position readiness check for a Boring Box."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from boring.position import PositionProvider


@dataclass(frozen=True)
class PositionCheckReport:
    passed: bool
    mode: str
    source: str | None
    lat: float | None
    lon: float | None
    checked_at: str
    failures: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def run_position_check(
    provider: PositionProvider,
    *,
    mode: str,
    expected_lat: float | None = None,
    expected_lon: float | None = None,
    tolerance_degrees: float = 0.0005,
    now: datetime | None = None,
) -> PositionCheckReport:
    position = provider.current()
    checked_at = (now or datetime.now(timezone.utc)).isoformat()
    if position is None:
        return PositionCheckReport(
            passed=False,
            mode=mode,
            source=None,
            lat=None,
            lon=None,
            checked_at=checked_at,
            failures=["position=missing"],
        )

    failures = _position_failures(
        mode=mode,
        source=position.source,
        lat=position.lat,
        lon=position.lon,
        expected_lat=expected_lat,
        expected_lon=expected_lon,
        tolerance_degrees=tolerance_degrees,
    )
    return PositionCheckReport(
        passed=not failures,
        mode=mode,
        source=position.source,
        lat=position.lat,
        lon=position.lon,
        checked_at=checked_at,
        failures=failures,
    )


def write_report(report: PositionCheckReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")


def _position_failures(
    *,
    mode: str,
    source: str,
    lat: float,
    lon: float,
    expected_lat: float | None,
    expected_lon: float | None,
    tolerance_degrees: float,
) -> list[str]:
    failures = []
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"static", "gpsd"}:
        failures.append(f"mode={mode or '-'}")
    if source != normalized_mode:
        failures.append(f"source={source or '-'}/{normalized_mode or '-'}")
    if not (-90 <= lat <= 90):
        failures.append(f"lat={lat}")
    if not (-180 <= lon <= 180):
        failures.append(f"lon={lon}")
    if normalized_mode == "static":
        if expected_lat is None or expected_lon is None:
            failures.append("expected_static_position=missing")
        else:
            if abs(lat - expected_lat) > tolerance_degrees:
                failures.append(f"lat_delta={abs(lat - expected_lat):.6f}")
            if abs(lon - expected_lon) > tolerance_degrees:
                failures.append(f"lon_delta={abs(lon - expected_lon):.6f}")
    return failures
