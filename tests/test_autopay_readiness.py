from __future__ import annotations

import json
from pathlib import Path

from boring.autopay_readiness import audit_autopay_readiness, write_report


def test_autopay_readiness_passes_with_complete_real_config(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    env = _ready_env(tmp_path)

    report = audit_autopay_readiness(env=env, endpoints_path=endpoints)

    assert report.passed is True
    assert all(check.ok for check in report.checks)


def test_autopay_readiness_fails_on_dry_run_when_real_required(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    env = _ready_env(tmp_path)
    env["PAYMENT_DRY_RUN"] = "true"

    strict = audit_autopay_readiness(env=env, endpoints_path=endpoints)
    rehearsal = audit_autopay_readiness(
        env=env,
        endpoints_path=endpoints,
        require_real_payment=False,
    )

    assert strict.passed is False
    assert any(check.name == "payment_dry_run" and not check.ok for check in strict.checks)
    assert rehearsal.passed is True


def test_autopay_readiness_fails_without_geofence_position(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    env = _ready_env(tmp_path)
    env["BOX_LAT"] = ""
    env["BOX_LON"] = ""
    env["POSITION_MODE"] = "static"

    report = audit_autopay_readiness(env=env, endpoints_path=endpoints)

    assert report.passed is False
    assert any(check.name == "geofence_position" and not check.ok for check in report.checks)


def test_autopay_readiness_fails_without_geofence_zones(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    env = _ready_env(tmp_path)
    env["PARKING_ZONES_PATH"] = str(tmp_path / "missing-zones.geojson")

    report = audit_autopay_readiness(env=env, endpoints_path=endpoints)

    assert report.passed is False
    assert any(check.name == "geofence_zones" and not check.ok for check in report.checks)


def test_autopay_readiness_fails_with_empty_geofence_zones(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    zones = tmp_path / "empty-zones.geojson"
    zones.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    env = _ready_env(tmp_path)
    env["PARKING_ZONES_PATH"] = str(zones)

    report = audit_autopay_readiness(env=env, endpoints_path=endpoints)

    assert report.passed is False
    check = [check for check in report.checks if check.name == "geofence_zones"][0]
    assert "features=0" in check.detail


def test_autopay_readiness_allows_missing_zones_when_geofence_disabled(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    env = _ready_env(tmp_path)
    env["BOX_REQUIRE_GEOFENCE"] = "false"
    env["PARKING_ZONES_PATH"] = str(tmp_path / "missing-zones.geojson")

    report = audit_autopay_readiness(env=env, endpoints_path=endpoints)

    assert report.passed is True
    check = [check for check in report.checks if check.name == "geofence_zones"][0]
    assert "required=false" in check.detail


def test_autopay_readiness_fails_when_payment_limits_are_invalid(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path)
    env = _ready_env(tmp_path)
    env["MAX_SESSION_AMOUNT_CENTS"] = "2000"
    env["MAX_DAILY_AMOUNT_CENTS"] = "1500"

    report = audit_autopay_readiness(env=env, endpoints_path=endpoints)

    assert report.passed is False
    assert any(check.name == "payment_limits" and not check.ok for check in report.checks)


def test_autopay_readiness_fails_without_har_artifact(tmp_path: Path):
    report = audit_autopay_readiness(
        env=_ready_env(tmp_path), endpoints_path=tmp_path / "missing.json"
    )

    assert report.passed is False
    assert any(check.name == "paybyphone_har_artifact" and not check.ok for check in report.checks)


def test_autopay_readiness_fails_when_har_flow_is_incomplete(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path, session_stop=False)

    report = audit_autopay_readiness(env=_ready_env(tmp_path), endpoints_path=endpoints)

    assert report.passed is False
    assert any(check.name == "paybyphone_har_artifact" and not check.ok for check in report.checks)


def test_autopay_readiness_fails_when_har_hint_is_missing(tmp_path: Path):
    endpoints = _write_endpoints(tmp_path, payment_method_id="")

    report = audit_autopay_readiness(env=_ready_env(tmp_path), endpoints_path=endpoints)

    assert report.passed is False
    check = [check for check in report.checks if check.name == "paybyphone_har_artifact"][0]
    assert "missing_hints=payment_method_id" in check.detail


def test_write_report_includes_passed(tmp_path: Path):
    report = audit_autopay_readiness(
        env=_ready_env(tmp_path), endpoints_path=_write_endpoints(tmp_path)
    )
    output = tmp_path / "reports" / "autopay.json"

    write_report(report, output)

    payload = json.loads(output.read_text())
    assert payload["passed"] is True


def _ready_env(tmp_path: Path) -> dict[str, str]:
    zones = _write_zones(tmp_path)
    return {
        "PAYMENT_MODE": "auto",
        "PAYMENT_PROVIDER": "paybyphone",
        "PAYMENT_DRY_RUN": "false",
        "DEFAULT_VEHICLE_PLATE": "AB-123-CD",
        "DEFAULT_DURATION_MINUTES": "15",
        "COOLDOWN_MINUTES": "15",
        "MAX_SESSION_AMOUNT_CENTS": "500",
        "MAX_DAILY_AMOUNT_CENTS": "1500",
        "PAYBYPHONE_USERNAME": "user",
        "PAYBYPHONE_PASSWORD": "secret",
        "PAYBYPHONE_API_BASE": "https://api.example.test",
        "PAYBYPHONE_AUTH_URL": "https://api.example.test/auth",
        "PAYBYPHONE_CLIENT_ID": "client",
        "PAYBYPHONE_RATE_OPTION_ID": "rate",
        "PAYBYPHONE_PAYMENT_METHOD_ID": "pm",
        "BOX_REQUIRE_GEOFENCE": "true",
        "POSITION_MODE": "static",
        "BOX_LAT": "50.6371",
        "BOX_LON": "3.0633",
        "PARKING_ZONES_PATH": str(zones),
    }


def _write_endpoints(
    tmp_path: Path,
    *,
    session_stop: bool = True,
    payment_method_id: str = "pm",
) -> Path:
    endpoints = tmp_path / "scripts" / "paybyphone_endpoints.json"
    endpoints.parent.mkdir(parents=True)
    endpoints.write_text(
        json.dumps(
            {
                "config_hints": {
                    "base_url": "https://api.example.test",
                    "auth_url": "https://api.example.test/auth",
                    "client_id": "client",
                    "rate_option_id": "rate",
                    "payment_method_id": payment_method_id,
                },
                "flow_summary": {
                    "auth": True,
                    "account_lookup": True,
                    "location_lookup": True,
                    "session_start": True,
                    "active_session_check": True,
                    "session_stop": session_stop,
                    "successful_statuses": 6,
                    "failed_statuses": 0,
                },
            }
        )
    )
    return endpoints


def _write_zones(tmp_path: Path) -> Path:
    zones = tmp_path / "data" / "lille_parking_zones.geojson"
    zones.parent.mkdir(parents=True, exist_ok=True)
    zones.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[3.0, 50.6], [3.1, 50.6], [3.1, 50.7], [3.0, 50.7], [3.0, 50.6]]
                            ],
                        },
                    }
                ],
            }
        )
    )
    return zones
