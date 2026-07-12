from __future__ import annotations

import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from boring.camera_readiness import CameraCheckReport
from boring.cli import app
from boring.network_readiness import NetworkCheckReport
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


def test_box_runtime_checks_can_include_systemd(tmp_path, monkeypatch):
    _patch_runtime_reports(monkeypatch)

    result = runner.invoke(
        app,
        ["box-runtime-checks", "--output-dir", str(tmp_path), "--include-systemd"],
    )

    assert result.exit_code == 0
    assert json.loads((tmp_path / "systemd-check.json").read_text())["passed"] is True


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
            timeout_seconds=3.0,
            recovery_command_configured=True,
            checked_at=checked_at,
            failures=[],
            error=None,
        ),
    )
    monkeypatch.setattr(
        "boring.cli.run_power_check",
        lambda **kwargs: PowerCheckReport(
            passed=True,
            battery_percent=82,
            charging=False,
            source="bat",
            battery_capacity_wh=100,
            estimated_draw_watts=8,
            estimated_runtime_hours=12.5,
            required_runtime_hours=10,
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
            exec_start="/opt/boring/.venv/bin/boring box-run",
            user="boring",
            checked_at=checked_at,
            failures=[],
            error=None,
        ),
    )
