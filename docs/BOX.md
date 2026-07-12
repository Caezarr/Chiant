# Boring Parking Box — production architecture

Objectif : un boitier anti-FPS headless. Il demarre seul, detecte les vehicules de controle, paie le minimum legal si la voiture est en zone payante, et alerte l'utilisateur si le boitier va manquer de batterie.

## Materiel cible

### Prototype robuste

- Raspberry Pi 5 8 Go
- Camera Module 3 Wide ou camera USB UVC 1080p
- SSD ou microSD endurance 64 Go
- UPS HAT expose via `/sys/class/power_supply`
- Alimentation allume-cigare USB-C PD 30 W
- Batterie tampon 20 000 mAh ou pack LiFePO4 dedie
- Option acceleration : Coral USB TPU apres export TFLite

### Prototype low-cost

- Raspberry Pi 4 4 Go
- Camera USB UVC 1080p
- Power bank pass-through 20 000 mAh
- Modele YOLOv8n en CPU, 1-3 FPS

Pi 4 est suffisant pour une demo. Pi 5 est le minimum confortable pour tourner 10h avec detection continue, logs, reseau et marge thermique.

Les variantes supportees sont versionnees dans `data/hardware_presets.json` :

- `pi4-low-cost` : demo Pi 4 4 Go, batterie 80 Wh minimum, recharge voiture 20 W minimum, benchmark cible 1 FPS.
- `pi5-production` : beta terrain Pi 5 8 Go, batterie 100 Wh minimum, recharge voiture 30 W minimum, benchmark cible 2 FPS.

Le fichier `deploy/pi/hardware-profile.json` doit declarer `preset_id`; `box-ready` echoue si le profil reel ne respecte pas le preset choisi.

## Runtime

Commande principale :

```bash
uv run boring box-run
```

Preflight avant de laisser la box seule :

```bash
uv run boring box-doctor
```

Le doctor verifie notamment : camera accessible, modele present, zones, position, dossier d'etat, reseau, paiement reel, autonomie theorique.

Burn-in avant beta terrain :

```bash
uv run boring box-burn-in --minutes 120 --interval 60 --output burn-in/pi5-daylight
```

La commande sonde camera, batterie, temperature et reseau, puis ecrit :

- `samples.jsonl` : une ligne par sonde.
- `report.json` : verdict synthetique, max temperature, min batterie, delta batterie, recharge vue, echecs camera/reseau.

Le burn-in echoue si la camera ou le reseau tombent, si la batterie passe en critique, ou si la temperature atteint `THERMAL_CRITICAL_C`. Pour un premier proto, faire au moins 2h branche puis 2h sur batterie afin que `charging_seen=true` et `discharging_seen=true`. Avant promesse 10h, faire un run complet en conditions voiture.

Gate final avant systemd / installation voiture :

```bash
cp deploy/pi/hardware-profile.example.json deploy/pi/hardware-profile.json
uv run boring vision-ready --require-edge-export
uv run boring vision-eval --dataset datasets/control_vehicle_v1 --model models/best.pt --split valid --frame-interval 1 --output reports/vision-eval.json
uv run boring vision-benchmark --model models/best.pt --device cpu --frames 120 --min-fps 2.0
uv run boring autopay-ready
uv run boring autopay-smoke --yes --output reports/autopay-smoke.json
uv run boring box-notify-test --output reports/notification-test.json
uv run boring box-ready --hardware-profile deploy/pi/hardware-profile.json --vision-eval-report reports/vision-eval.json --benchmark-report reports/vision-benchmark.json --autopay-smoke-report reports/autopay-smoke.json --notification-report reports/notification-test.json --burn-in-report burn-in/pi5-daylight/report.json --storage-path /var/lib/boring/events.jsonl
uv run boring box-evidence-pack --output reports/evidence-pack.json
```

`hardware-profile.json` declare la box reellement installee : modele Pi, RAM, camera, stockage, UPS, batterie, charge voiture et reseau. `vision-benchmark` produit `reports/vision-benchmark.json` pour savoir si le Pi cible tient le FPS voulu; `box-ready` exige le `runtime.min_benchmark_fps` du preset hardware, donc un profil `pi5-production` doit etre benchmarke a 2 FPS minimum. `reports/vision-eval.json` prouve que le modele atteint les seuils terrain: recall >= 90% et faux positifs <= 1/h. `autopay-smoke` demarre une vraie session minimale, verifie qu'elle est active, l'arrete, verifie que l'arret a supprime la session active, puis produit `reports/autopay-smoke.json`. Lance-le apres la config finale: `box-ready` refuse un smoke issu d'un autre `PAYMENT_PROVIDER`, d'une autre `DEFAULT_VEHICLE_PLATE`, d'une autre `PAYBYPHONE_LOCATION_ID` si cette zone est forcee, ou d'un montant superieur a `MAX_SESSION_AMOUNT_CENTS`. `box-notify-test` envoie un vrai payload au webhook et produit `reports/notification-test.json`. `box-ready` agrege les preuves locales : hardware Pi 4/5, vision, evaluation qualite, benchmark FPS sur hardware cible, autopaiement reel prouve, budget energie, recovery reseau, notification testee, espace disque libre et rapport `box-burn-in`. Par defaut, il exige un burn-in de 10h, `PAYMENT_DRY_RUN=false`, un smoke autopaiement non dry-run avec montant positif et `stop_verified=true`, un export edge `best.onnx` ou `best.tflite`, un profil hardware valide, un budget batterie/recharge coherent, `NETWORK_RECOVERY_COMMAND`, `BORING_NOTIFY_WEBHOOK_URL` ou `NTFY_WEBHOOK_URL`, un test notification 2xx, une preuve que la batterie a ete vue en charge, et des rapports datant de moins de `BOX_READINESS_MAX_REPORT_AGE_HOURS` heures (72h par defaut). `BATTERY_CAPACITY_WH` et `VEHICLE_CHARGE_WATTS` doivent correspondre aux valeurs du profil hardware a 1 Wh/W pres.

Si `BOX_EVENT_LOG_PATH` existe, `box-ready` scanne aussi le journal runtime depuis `burn-in.started_at` et refuse les evenements bloquants: crash service, batterie critique, temperature critique, stockage faible, reseau offline, notification ratee, paiement bloque offline/sans position/batterie critique, ou recovery reseau echoue.

`box-evidence-pack` regroupe ensuite les rapports terrain dans `reports/evidence-pack.json` pour audit, partage ou support. Chaque item inclut `size_bytes` et `sha256`; si un rapport est modifie apres generation du pack, son empreinte ne correspond plus.

Pour une repetition sans paiement reel :

```bash
uv run boring box-ready --allow-dry-run --allow-missing-autopay-smoke --allow-missing-edge-export --allow-missing-charge-validation --allow-missing-network-recovery --allow-missing-notification-webhook --allow-missing-notification-test --min-burn-in-hours 2
```

Pour rejouer un dossier ancien en local sans pretendre a une installation, `BOX_READINESS_MAX_REPORT_AGE_HOURS=0` desactive uniquement le check de fraicheur.

Variables critiques :

```bash
PAYMENT_MODE=auto
PAYMENT_DRY_RUN=false
DEFAULT_VEHICLE_PLATE=AB-123-CD
POSITION_MODE=static
BOX_LAT=50.6371
BOX_LON=3.0633
GPSD_HOST=127.0.0.1
GPSD_PORT=2947
BOX_REQUIRE_GEOFENCE=true
DETECTION_MODEL=models/best.pt
DETECTION_TARGET_LABELS=control_vehicle
DETECTION_DEVICE=cpu
DETECTION_FPS=2.0
LOW_POWER_DETECTION_FPS=0.5
CAMERA_DEVICE=0
BORING_NOTIFY_WEBHOOK_URL=https://...
BATTERY_CAPACITY_WH=100
ESTIMATED_DRAW_WATTS=8.0
REQUIRED_RUNTIME_HOURS=10.0
POWER_RESERVE_PERCENT=15.0
VEHICLE_CHARGE_WATTS=30.0
DAILY_DRIVE_RECHARGE_HOURS=1.0
CHARGE_EFFICIENCY=0.85
BOX_STATE_PATH=/var/lib/boring/state.json
BOX_EVENT_LOG_PATH=/var/lib/boring/events.jsonl
BOX_EVENT_LOG_MAX_BYTES=5000000
BOX_EVENT_LOG_BACKUPS=3
BOX_DISK_MIN_FREE_MB=512
BOX_DISK_CHECK_SECONDS=300
NETWORK_PROBE_TARGET=1.1.1.1:443
NETWORK_RECOVERY_COMMAND=sh /opt/boring/deploy/pi/network-recover.example.sh
NETWORK_RECOVERY_COOLDOWN_SECONDS=300
NETWORK_RECOVERY_TIMEOUT_SECONDS=20
THERMAL_WARNING_C=75.0
THERMAL_CRITICAL_C=85.0
```

Par defaut, `PAYMENT_DRY_RUN=true`. C'est volontaire : un clone du repo ne doit jamais declencher un paiement reel par accident.

`POSITION_MODE=static` suffit pour une demo a emplacement fixe. Pour une box multi-arrets, utiliser `POSITION_MODE=gpsd` avec un GPS USB/HAT et gpsd local. La zone payante est verifiee au moment du trigger, pas seulement au demarrage.

`BOX_STATE_PATH` persiste le dernier paiement. Si systemd redemarre la box, le cooldown reste actif et evite un second paiement immediat.
`BOX_EVENT_LOG_PATH` garde une trace locale JSONL des evenements critiques : demarrage, reseau offline/recovered, batterie faible, temperature elevee/revenue, disque faible, paiement bloque, paiement reussi, crash. La rotation est bornee par `BOX_EVENT_LOG_MAX_BYTES` et `BOX_EVENT_LOG_BACKUPS` pour ne pas remplir la carte SD.
`BOX_DISK_MIN_FREE_MB` declenche une alerte si la partition qui porte le journal/etat persistant descend trop bas.

## Service systemd

Installer le repo dans `/opt/boring`, copier `deploy/pi/box.env.example` vers `/opt/boring/.env`, puis installer l'unit fournie :

```bash
DRY_RUN=1 ./deploy/pi/install.sh
sudo ./deploy/pi/install.sh
```

Commandes :

```bash
sudo systemctl daemon-reload
sudo systemctl enable boring-box
sudo systemctl start boring-box
journalctl -u boring-box -f
systemctl show boring-box -p WatchdogUSec -p NRestarts
```

L'unit fournie utilise `Type=notify` et `WatchdogSec=120`. Le runtime envoie `READY=1`, puis `WATCHDOG=1` depuis la boucle de monitoring. Si le process reste vivant mais bloque sa boucle interne, systemd redemarre la box.

## Batterie et notifications

Le runtime lit `/sys/class/power_supply/*/capacity`. Beaucoup de UPS HAT exposent la batterie ici. Si la batterie descend sous `BATTERY_LOW_PERCENT` sans etre en charge, une notification est envoyee. Sous `BATTERY_CRITICAL_PERCENT`, une notification critique est envoyee et l'autopaiement est bloque avec `payment_skipped_battery_critical`. Les alertes sont rearmees quand la batterie charge ou repasse au-dessus de `BATTERY_RECOVERED_PERCENT`, et l'evenement `battery_recovered` est journalise.
Il lit aussi `/sys/class/thermal/thermal_zone*/temp` et alerte au-dessus de `THERMAL_WARNING_C`, puis `THERMAL_CRITICAL_C`. C'est important pour une box dans un habitacle au soleil : avant la beta terrain, verifier avec `journalctl -u boring-box -f` que le Pi ne throttle pas pendant une detection longue.
Le runtime surveille aussi le reseau avec `NETWORK_PROBE_TARGET`. Si la box perd le reseau, elle notifie l'utilisateur car l'autopaiement risque d'echouer. Si `NETWORK_RECOVERY_COMMAND` est configure, il tente aussi une recuperation au plus une fois par `NETWORK_RECOVERY_COOLDOWN_SECONDS`, par exemple `sh /opt/boring/deploy/pi/network-recover.example.sh` sur Raspberry Pi OS ou un script maison qui redemarre le modem 4G. Chaque tentative est journalisee avec `network_recovery_attempted`.

Quand la batterie passe sous `BATTERY_LOW_PERCENT` sans etre en charge, ou quand la temperature depasse `THERMAL_WARNING_C`, la box passe en mode economie et utilise `LOW_POWER_DETECTION_FPS`. Le retour en charge, le retour au-dessus de `BATTERY_LOW_PERCENT`, ou le retour sous le seuil thermique restaure `DETECTION_FPS`. Les transitions sont journalisees avec `power_saver_changed`.

Pour le prototype, utiliser un webhook simple : ntfy, Pushover, Discord webhook, Slack webhook, ou un endpoint maison. Le payload envoye est :

```json
{"title": "Boring Box — batterie faible", "message": "18% restants", "sound": true}
```

Avant installation, tester le canal avec le meme endpoint que le boitier :

```bash
BORING_NOTIFY_WEBHOOK_URL=https://... uv run boring box-doctor
BORING_NOTIFY_WEBHOOK_URL=https://... uv run boring box-notify-test --output reports/notification-test.json
```

`box-doctor` echoue si aucun webhook n'est configure, car une box 10h sans canal batterie faible n'est pas installable. `box-notify-test` echoue si le endpoint ne retourne pas 2xx; verifier ensuite la reception sur le telephone avant de lancer le burn-in long. `box-ready` verifie aussi que `reports/notification-test.json` cible le meme host que le webhook configure, donc relance `box-notify-test` apres tout changement de canal. Pendant le runtime, si une alerte batterie faible/critique ne part sur aucun canal externe, l'evenement `notification_failed` est journalise dans `BOX_EVENT_LOG_PATH`.

## Autonomie 10h

Budget de depart :

- Pi 5 + camera USB : 5-8 W selon charge
- 10h : 50-80 Wh utiles
- Une power bank 20 000 mAh annonce souvent 70-74 Wh nominaux, moins apres conversion

Conclusion : pour 10h fiable, viser 100 Wh nominaux ou reduire l'inference a 1-2 FPS hors zone critique. La box doit etre branchee quand la voiture roule pour recharger, mais doit pouvoir tenir la journee quand elle reste garee.

`box-ready` et `box-doctor` calculent le budget energie avec :

```text
usable_wh = BATTERY_CAPACITY_WH * (1 - POWER_RESERVE_PERCENT / 100)
parked_runtime_h = usable_wh / ESTIMATED_DRAW_WATTS
charge_surplus_w = VEHICLE_CHARGE_WATTS - ESTIMATED_DRAW_WATTS
daily_recovered_wh = charge_surplus_w * DAILY_DRIVE_RECHARGE_HOURS * CHARGE_EFFICIENCY
```

Le gate passe seulement si `parked_runtime_h >= REQUIRED_RUNTIME_HOURS` et si la recharge voiture fournit plus que la consommation instantanee de la box. Exemple Pi 5 prudent : `100 Wh`, `8 W`, reserve `15%` donne `85 Wh utiles`, soit `10.6h` gare. Avec une entree voiture `30 W`, le surplus est `22 W`; une heure de roulage recupere environ `18.7 Wh` a `85%` de rendement.

Reglages de depart :

- Pi 4 CPU, camera USB : `ESTIMATED_DRAW_WATTS=6.0`, `DETECTION_FPS=1.0`, batterie cible `80-100 Wh`.
- Pi 5 CPU, camera USB : `ESTIMATED_DRAW_WATTS=8.0`, `DETECTION_FPS=2.0`, batterie cible `100 Wh`.
- Pi 5 + accelerateur/SSD/4G : mesurer au wattmetre et mettre `ESTIMATED_DRAW_WATTS=10-12`.
- Alim voiture : viser USB-C PD `30 W` minimum. Une entree `5V/2A` peut maintenir un Pi leger, mais ne recharge pas assez vite pendant l'inference.

La preuve terrain doit venir de `box-burn-in` : `min_battery_percent`, `battery_delta_percent`, `charging_seen`, `discharging_seen`, `max_temp_c`, `camera_failures=0`, `network_failures=0`, et `passed=true`.

## Gaps avant beta terrain

- GPS reel ou position smartphone synchronisee. `BOX_LAT/BOX_LON` suffit pour une demo statique, pas pour multi-arrets.
- Export modele edge : TFLite/ONNX + benchmark Pi 4/Pi 5.
- PayByPhone `dry_run=false` valide sur HAR reel et `autopay-smoke` passe sur session minimale.
- Boitier thermique : test reel Pi 5 dans habitacle au soleil, avec temperature loggee et detection continue.
- Test terrain du recovery reseau avec le vrai Wi-Fi/4G choisi.
