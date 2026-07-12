from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from typer.testing import CliRunner

from boring.camera_readiness import CameraCheckReport
from boring.cli import app
from boring.network_readiness import NetworkCheckReport
from boring.payment.base import ParkingSession, PaymentProvider
from boring.position_readiness import PositionCheckReport
from boring.power_readiness import PowerCheckReport
from boring.systemd_readiness import SystemdCheckReport


runner = CliRunner()


def test_box_runtime_checks_writes_runtime_reports(tmp_path, monkeypatch):
    _patch_runtime_reports(monkeypatch)

    result = runner.invoke(app, ["box-runtime-checks", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    assert json.loads((tmp_path / "camera-check.json").read_text())["passed"] is True
    assert json.loads((tmp_path / "position-check.json").read_text())["passed"] is True
    assert json.loads((tmp_path / "network-check.json").read_text())["passed"] is True
    assert json.loads((tmp_path / "power-check.json").read_text())["passed"] is True
    assert not (tmp_path / "systemd-check.json").exists()


def test_box_runtime_checks_uses_network_probe_timeout_env(tmp_path, monkeypatch):
    _patch_runtime_reports(monkeypatch)
    monkeypatch.setenv("NETWORK_PROBE_TIMEOUT_SECONDS", "4.5")

    result = runner.invoke(app, ["box-runtime-checks", "--output-dir", str(tmp_path)])

    assert result.exit_code == 0
    payload = json.loads((tmp_path / "network-check.json").read_text())
    assert payload["timeout_seconds"] == 4.5


def test_box_runtime_checks_can_include_systemd(tmp_path, monkeypatch):
    _patch_runtime_reports(monkeypatch)

    result = runner.invoke(
        app,
        ["box-runtime-checks", "--output-dir", str(tmp_path), "--include-systemd"],
    )

    assert result.exit_code == 0
    assert json.loads((tmp_path / "systemd-check.json").read_text())["passed"] is True


def test_box_evidence_pack_can_override_model_path(tmp_path, monkeypatch):
    captured = {}

    def build_pack_spy(paths, **kwargs):
        captured["paths"] = paths
        captured["kwargs"] = kwargs
        return SimpleNamespace(items=[], passed=True)

    def write_pack_spy(pack, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("{}")

    model_path = tmp_path / "custom" / "model.pt"
    monkeypatch.setattr("boring.cli.build_evidence_pack", build_pack_spy)
    monkeypatch.setattr("boring.cli.write_pack", write_pack_spy)

    result = runner.invoke(
        app,
        [
            "box-evidence-pack",
            "--model",
            str(model_path),
            "--output",
            str(tmp_path / "pack.json"),
        ],
    )

    assert result.exit_code == 0
    assert captured["paths"]["edge_export"] == model_path
    assert captured["kwargs"]["max_report_age_hours"] == 72.0


def test_box_ready_uses_runtime_paths_from_env(tmp_path, monkeypatch):
    captured = {}

    def audit_spy(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            checks=[SimpleNamespace(name="state_path", ok=True, detail="ok")],
            passed=True,
        )

    def write_report_spy(report, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("{}")

    state_path = tmp_path / "custom-state" / "state.json"
    event_log_path = tmp_path / "custom-events" / "events.jsonl"
    monkeypatch.setenv("BOX_STATE_PATH", str(state_path))
    monkeypatch.setenv("BOX_EVENT_LOG_PATH", str(event_log_path))
    monkeypatch.setattr("boring.cli.audit_production_readiness", audit_spy)
    monkeypatch.setattr("boring.cli.write_production_report", write_report_spy)

    result = runner.invoke(
        app,
        [
            "box-ready",
            "--output",
            str(tmp_path / "box-readiness.json"),
        ],
    )

    assert result.exit_code == 0
    assert captured["state_path"] == state_path
    assert captured["storage_path"] == event_log_path


def test_autopay_smoke_cli_uses_env_credentials_and_duration(tmp_path, monkeypatch):
    provider = _CliPaymentProvider()
    monkeypatch.setattr("boring.cli.make_payment_provider", lambda: provider)
    monkeypatch.setenv("PAYBYPHONE_USERNAME", "user@example.test")
    monkeypatch.setenv("PAYBYPHONE_PASSWORD", "secret")
    monkeypatch.setenv("DEFAULT_DURATION_MINUTES", "7")
    monkeypatch.setenv("MAX_SESSION_AMOUNT_CENTS", "500")
    captured = {}

    def run_smoke_spy(**kwargs):
        captured.update(kwargs)
        return _run_real_autopay_smoke(**kwargs)

    monkeypatch.setattr("boring.cli.run_autopay_smoke", run_smoke_spy)

    result = runner.invoke(
        app,
        [
            "autopay-smoke",
            "--yes",
            "--plate",
            "AB-123-CD",
            "--lat",
            "50.6371",
            "--lon",
            "3.0633",
            "--output",
            str(tmp_path / "autopay-smoke.json"),
        ],
    )

    assert result.exit_code == 0
    assert provider.login_args == ("user@example.test", "secret")
    assert captured["max_session_amount_cents"] == 500
    payload = json.loads((tmp_path / "autopay-smoke.json").read_text())
    assert payload["passed"] is True
    assert payload["duration_minutes"] == 7


def test_pay_now_cli_uses_env_credentials(monkeypatch):
    provider = _CliPaymentProvider()
    monkeypatch.setattr("boring.cli.make_payment_provider", lambda: provider)
    monkeypatch.setenv("PAYBYPHONE_USERNAME", "user@example.test")
    monkeypatch.setenv("PAYBYPHONE_PASSWORD", "secret")

    result = runner.invoke(
        app,
        [
            "pay-now",
            "--plate",
            "AB-123-CD",
            "--duration",
            "5",
            "--lat",
            "50.6371",
            "--lon",
            "3.0633",
        ],
    )

    assert result.exit_code == 0
    assert provider.login_args == ("user@example.test", "secret")


class _CliPaymentProvider(PaymentProvider):
    name = "paybyphone"

    def __init__(self) -> None:
        self.dry_run = False
        self.login_args: tuple[str, str] | None = None
        self.session: ParkingSession | None = None

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def get_zone_id(self, lat: float, lon: float) -> str:
        return "zone-1"

    def start_session(
        self,
        vehicle_plate: str,
        location_id: str,
        duration_minutes: int,
    ) -> ParkingSession:
        self.session = ParkingSession(
            provider=self.name,
            session_id="session-1",
            vehicle_plate=vehicle_plate,
            location_id=location_id,
            start=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc),
            end=datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
            + timedelta(minutes=duration_minutes),
            amount_cents=120,
        )
        return self.session

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        return self.session

    def stop_session(self, session_id: str) -> None:
        self.session = None


def _run_real_autopay_smoke(**kwargs):
    from boring.autopay_smoke import run_autopay_smoke

    return run_autopay_smoke(**kwargs)


def _patch_runtime_reports(monkeypatch) -> None:
    checked_at = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    monkeypatch.setattr(
        "boring.cli.run_camera_check",
        lambda **kwargs: CameraCheckReport(
            passed=True,
            device_index=0,
            width=1280,
            height=720,
            min_width=640,
            min_height=480,
            checked_at=checked_at,
            failures=[],
            error=None,
        ),
    )
    monkeypatch.setattr(
        "boring.cli.run_position_check",
        lambda *args, **kwargs: PositionCheckReport(
            passed=True,
            mode="static",
            source="static",
            lat=50.6371,
            lon=3.0633,
            gpsd_host=None,
            gpsd_port=None,
            checked_at=checked_at,
            failures=[],
        ),
    )
    monkeypatch.setattr(
        "boring.cli.run_network_check",
        lambda **kwargs: NetworkCheckReport(
            passed=True,
            target="1.1.1.1:443",
            online=True,
            timeout_seconds=kwargs["timeout_seconds"],
            recovery_command_configured=True,
            recovery_command="systemctl restart NetworkManager",
            checked_at=checked_at,
            failures=[],
            error=None,
        ),
    )
    monkeypatch.setattr(
        "boring.cli.run_power_check",
        lambda **kwargs: PowerCheckReport(
            passed=True,
            battery_percent=92,
            charging=False,
            source="bat",
            battery_capacity_wh=100,
            critical_reserve_wh=10,
            available_battery_wh=82,
            estimated_draw_watts=8,
            estimated_runtime_hours=10.25,
            required_runtime_hours=10,
            battery_critical_percent=10,
            checked_at=checked_at,
            failures=[],
        ),
    )
    monkeypatch.setattr(
        "boring.cli.run_systemd_check",
        lambda service: SystemdCheckReport(
            service=service,
            passed=True,
            enabled_state="enabled",
            active_state="active",
            sub_state="running",
            unit_file_state="enabled",
            type="notify",
            watchdog_usec=30_000_000,
            main_pid=1234,
            n_restarts=0,
            exec_start="/opt/boring/.venv/bin/boring box-run",
            user="boring",
            checked_at=checked_at,
            failures=[],
            error=None,
        ),
    )
