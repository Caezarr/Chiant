from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pi_install_script_is_idempotent_and_conservative():
    script = (ROOT / "deploy" / "pi" / "install.sh").read_text()

    assert "DRY_RUN" in script
    assert "id boring" in script
    assert 'if [ ! -f "$INSTALL_DIR/.env" ]' in script
    assert "hardware-profile.example.json" in script
    assert "--exclude datasets" in script
    assert "START_SERVICE=0" in script
    assert "SKIP_SYNC=0" in script
    assert "--skip-sync" in script
    assert "uv sync --no-dev" in script
    assert "uv run boring --help >/dev/null" in script
    assert "su -s /bin/sh boring -c" in script
    assert "systemctl restart boring-box" in script
    assert 'if [ "$START_SERVICE" = "1" ]' in script
    assert "render_service" in script


def test_systemd_unit_runs_as_box_user_with_required_groups():
    unit = (ROOT / "deploy" / "systemd" / "boring-box.service").read_text()

    assert "User=boring" in unit
    assert "SupplementaryGroups=video gpio i2c netdev" in unit
    assert "WatchdogSec=120" in unit
    assert "ReadWritePaths=/opt/boring /var/lib/boring" in unit


def test_pi_install_renders_systemd_paths_from_install_options(tmp_path: Path):
    env = os.environ.copy()
    env["DRY_RUN"] = "1"

    result = subprocess.run(
        [
            "sh",
            str(ROOT / "deploy" / "pi" / "install.sh"),
            "--source",
            str(ROOT),
            "--install-dir",
            str(tmp_path / "app"),
            "--state-dir",
            str(tmp_path / "state"),
            "--skip-sync",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert f"INSTALL_DIR={tmp_path / 'app'}" in result.stdout
    assert f"STATE_DIR={tmp_path / 'state'}" in result.stdout
