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
uv run boring box-doctor
uv run boring box-runtime-checks --output-dir reports
uv run boring box-burn-in --minutes 120 --interval 60 --output burn-in/pi-first-run
uv run boring autopay-smoke --yes --output reports/autopay-smoke.json
uv run boring box-notify-test --output reports/notification-test.json

sudo systemctl enable boring-box
sudo systemctl start boring-box
systemctl show boring-box -p Type -p WatchdogUSec -p NRestarts
uv run boring box-systemd-check --output reports/systemd-check.json
uv run boring box-ready --hardware-profile deploy/pi/hardware-profile.json --vision-eval-report reports/vision-eval.json --autopay-smoke-report reports/autopay-smoke.json --notification-report reports/notification-test.json --burn-in-report burn-in/pi-first-run/report.json --min-burn-in-hours 2
uv run boring box-evidence-pack --output reports/evidence-pack.json
```

`install.sh` cree l'utilisateur `boring`, prepare `/opt/boring` et `/var/lib/boring`, copie le repo en excluant `.git`, `.venv`, `datasets`, `runs` et `frames`, lance `uv sync --no-dev` sous l'utilisateur `boring`, verifie que la CLI demarre, installe l'unit systemd, puis laisse le service arrete sauf si tu passes `--start`. Passe `--skip-sync` seulement pour une copie/repetition rapide ou si tu as deja synchronise le runtime.

## First boot checks

```bash
journalctl -u boring-box -f
v4l2-ctl --list-devices
uv run boring box-doctor
uv run boring box-burn-in --minutes 120 --interval 60 --output burn-in/pi-daylight
```

`box-doctor` doit afficher `OK camera accessible` avant installation systemd. Do not set `PAYMENT_DRY_RUN=false` before a real PayByPhone HAR has been validated and `autopay-smoke` has passed with a minimal paid session.
`hardware-profile.json` doit representer le boitier reel : `preset_id` (`pi4-low-cost` ou `pi5-production`), RAM, camera, stockage endurance, UPS expose via `/sys/class/power_supply`, batterie, charge voiture, reseau et FPS runtime. Ne garde pas l'exemple tel quel si le hardware differe. Les champs `power.battery_capacity_wh` et `power.vehicle_charge_watts` doivent rester coherents avec `BATTERY_CAPACITY_WH` et `VEHICLE_CHARGE_WATTS` dans `.env`.
`NETWORK_RECOVERY_COMMAND` doit correspondre au reseau reel du boitier. L'exemple `sh /opt/boring/deploy/pi/network-recover.example.sh` relance la connectivite via `nmcli`; remplace-le par un script dedie si tu utilises un modem 4G ou un routeur Wi-Fi dedie.
`BOX_STATE_PATH` doit rester dans `/var/lib/boring`; la box l'ecrit via remplacement atomique pour reduire les corruptions en cas de coupure, et si ce fichier devient illisible, elle bloque l'autopaiement avec `payment_skipped_state_corrupt` au lieu de repartir avec un cooldown vide.
`box-runtime-checks` ecrit `reports/camera-check.json`, `reports/position-check.json`, `reports/network-check.json` et `reports/power-check.json`.
`box-camera-check` ecrit `reports/camera-check.json`. La camera doit s'ouvrir, retourner une frame et respecter la resolution minimale, 640x480 par defaut.
`box-position-check` ecrit `reports/position-check.json`. En `POSITION_MODE=static`, il verifie `BOX_LAT/BOX_LON`; en `POSITION_MODE=gpsd`, il doit obtenir une position depuis gpsd.
`box-network-check` ecrit `reports/network-check.json`. La cible `NETWORK_PROBE_TARGET` doit etre joignable et `NETWORK_RECOVERY_COMMAND` doit etre configure.
`box-power-check` ecrit `reports/power-check.json`. La jauge batterie/UPS doit etre visible dans `/sys/class/power_supply`, avec un pourcentage et un statut charge/decharge exploitables. Si la jauge disparait pendant le runtime, la box journalise `battery_sensor_missing`, notifie l'utilisateur et bloque l'autopaiement jusqu'au retour de la jauge.
`box-burn-in` ecrit `report.json` et `samples.jsonl`. Avant beta terrain, garder un rapport avec `passed=true`, `camera_failures=0`, `network_failures=0`, `charging_seen=true`, `discharging_seen=true`, `max_temp_c` present et sous `THERMAL_CRITICAL_C`, pas de batterie critique et pas de temperature critique.
`box-systemd-check` ecrit `reports/systemd-check.json` apres installation et demarrage du service. Il doit voir `boring-box.service` enabled, active/running, `Type=notify`, watchdog actif et utilisateur `boring`.
`box-ready` est le gate final : pour une vraie promesse 10h, relancer avec `--min-burn-in-hours 10` sur un burn-in voiture complet et un `reports/autopay-smoke.json` issu d'un paiement reel minimal. Le fichier `samples.jsonl` doit rester a cote du `report.json` burn-in: `box-ready` verifie que les samples bruts concordent avec le nombre d'echantillons, camera/reseau, batterie minimum et temperature max du rapport. Les rapports critiques doivent etre recents; par defaut `BOX_READINESS_MAX_REPORT_AGE_HOURS=72`, y compris les rapports runtime qui exposent `checked_at`. `BOX_STATE_PATH` doit etre absolu et son dossier parent doit permettre une ecriture atomique. `BOX_EVENT_LOG_PATH` est requis en prod; il doit contenir des `heartbeat` proches du debut et de la fin du burn-in, et les evenements runtime bloquants font echouer le gate. Les rapports `box-camera-check`, `box-position-check`, `box-network-check`, `box-power-check` et `box-systemd-check` sont requis par defaut.
`box-evidence-pack` regroupe les rapports terrain, `deploy/pi/hardware-profile.json`, `scripts/paybyphone_endpoints.json`, `burn-in/samples.jsonl` et `/var/lib/boring/events.jsonl` dans `reports/evidence-pack.json`. Chaque rapport doit exposer `passed=true`; `box-readiness.json` doit contenir tous les checks critiques du gate final; les rapports camera/position/reseau/energie/systemd/burn-in doivent aussi contenir leurs metriques runtime attendues, pas seulement un booleen. Le profil hardware doit passer l'audit preset Pi/camera/stockage/batterie/charge voiture/reseau. `vision-eval` doit prouver recall/FP/h dans les seuils, frames et heures evaluees positives, zero image invalide, modele et dataset renseignes. `vision-benchmark` doit prouver FPS sur frames positives avec modele et device renseignes. `autopay-smoke` doit prouver un paiement non dry-run avec session active verifiee, montant positif, stop appele et stop verifie. `box-notify-test` doit prouver un endpoint 2xx avec host, titre et message. Le fichier PayByPhone doit contenir les `config_hints` critiques et le flow auth/location/start/active/stop issu du HAR. Les samples burn-in doivent etre du JSONL valide avec camera/reseau OK et metriques batterie/temperature presentes. Le journal runtime doit etre du JSONL valide, contenir des `heartbeat` au debut et a la fin du burn-in, et ne contenir aucun evenement bloquant. Le pack inclut aussi `format`, `size_bytes` et `sha256` pour chaque preuve presente.
L'unit systemd utilise `Type=notify` et `WatchdogSec=120`: si la boucle interne ne ping plus systemd, le service est redemarre automatiquement.
