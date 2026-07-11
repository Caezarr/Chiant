from __future__ import annotations

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
    assert "systemctl restart boring-box" in script
    assert 'if [ "$START_SERVICE" = "1" ]' in script


def test_systemd_unit_runs_as_box_user_with_required_groups():
    unit = (ROOT / "deploy" / "systemd" / "boring-box.service").read_text()

    assert "User=boring" in unit
    assert "SupplementaryGroups=video gpio i2c netdev" in unit
    assert "WatchdogSec=120" in unit
    assert "ReadWritePaths=/opt/boring /var/lib/boring" in unit
