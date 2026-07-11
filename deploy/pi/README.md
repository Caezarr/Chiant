# Raspberry Pi deployment

This folder contains deployment assets for the Boring Parking Box.

## Target OS

- Raspberry Pi OS Lite 64-bit
- Python 3.12
- `uv`
- Camera visible as `/dev/video0` or another UVC device
- Optional GPS exposed through gpsd for multi-stop use
- Optional UPS HAT exposing `/sys/class/power_supply/*/capacity`
- Thermal sensors exposed through `/sys/class/thermal/thermal_zone*/temp`

## Install sketch

```bash
DRY_RUN=1 ./deploy/pi/install.sh
sudo ./deploy/pi/install.sh
cd /opt/boring
uv sync --no-dev
uv run boring box-doctor
uv run boring box-burn-in --minutes 120 --interval 60 --output burn-in/pi-first-run
uv run boring autopay-smoke --yes --output reports/autopay-smoke.json
uv run boring box-notify-test --output reports/notification-test.json
uv run boring box-ready --hardware-profile deploy/pi/hardware-profile.json --vision-eval-report reports/vision-eval.json --autopay-smoke-report reports/autopay-smoke.json --notification-report reports/notification-test.json --burn-in-report burn-in/pi-first-run/report.json --min-burn-in-hours 2

sudo systemctl enable boring-box
sudo systemctl start boring-box
systemctl show boring-box -p Type -p WatchdogUSec -p NRestarts
```

`install.sh` cree l'utilisateur `boring`, prepare `/opt/boring` et `/var/lib/boring`, copie le repo en excluant `.git`, `.venv`, `datasets`, `runs` et `frames`, installe l'unit systemd, puis laisse le service arrete sauf si tu passes `--start`.

## First boot checks

```bash
journalctl -u boring-box -f
v4l2-ctl --list-devices
uv run boring box-doctor
uv run boring box-burn-in --minutes 120 --interval 60 --output burn-in/pi-daylight
```

`box-doctor` doit afficher `OK camera accessible` avant installation systemd. Do not set `PAYMENT_DRY_RUN=false` before a real PayByPhone HAR has been validated and `autopay-smoke` has passed with a minimal paid session.
`hardware-profile.json` doit representer le boitier reel : Pi 4/Pi 5, RAM, camera, stockage endurance, UPS expose via `/sys/class/power_supply`, batterie, charge voiture et reseau. Ne garde pas l'exemple tel quel si le hardware differe. Les champs `power.battery_capacity_wh` et `power.vehicle_charge_watts` doivent rester coherents avec `BATTERY_CAPACITY_WH` et `VEHICLE_CHARGE_WATTS` dans `.env`.
`NETWORK_RECOVERY_COMMAND` doit correspondre au reseau reel du boitier. L'exemple `sh /opt/boring/deploy/pi/network-recover.example.sh` relance la connectivite via `nmcli`; remplace-le par un script dedie si tu utilises un modem 4G ou un routeur Wi-Fi dedie.
`box-burn-in` ecrit `report.json` et `samples.jsonl`. Avant beta terrain, garder un rapport avec `passed=true`, `camera_failures=0`, `network_failures=0`, `charging_seen=true`, `discharging_seen=true`, pas de batterie critique et pas de temperature critique.
`box-ready` est le gate final : pour une vraie promesse 10h, relancer avec `--min-burn-in-hours 10` sur un burn-in voiture complet et un `reports/autopay-smoke.json` issu d'un paiement reel minimal.
L'unit systemd utilise `Type=notify` et `WatchdogSec=120`: si la boucle interne ne ping plus systemd, le service est redemarre automatiquement.
