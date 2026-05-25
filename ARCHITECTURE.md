# Architecture

> Document technique. Pour le contexte produit, voir [README.md](README.md).
> Pour les actions humaines, voir [HUMAN-TODO.md](HUMAN-TODO.md).

## Vue d'ensemble

```
            ┌─────────────────────────────────────────────────────────────┐
            │                       boring.cli                            │
            │   commands: version, capture, detect, run, pay-now          │
            └────────────────────────────┬────────────────────────────────┘
                                         │
            ┌────────────────────────────▼────────────────────────────────┐
            │                       boring.glue                           │
            │            run_pipeline()  +  process_trigger()             │
            └─┬──────────┬─────────────┬──────────────┬───────────────────┘
              │          │             │              │
              ▼          ▼             ▼              ▼
        ┌──────────┐ ┌────────┐ ┌──────────────┐ ┌─────────────┐
        │ capture  │ │ detect │ │   geofence   │ │   payment   │
        │          │ │        │ │              │ │             │
        │  cv2 VC  │ │ YOLOv8 │ │  Shapely     │ │ PaymentProv │
        │  webcam  │ │ + Tr.  │ │  point-in-   │ │ (interface) │
        │          │ │ Tracker│ │  polygon     │ │             │
        └──────────┘ └────────┘ └──────────────┘ └──────┬──────┘
                                                        │
              ┌────────────────────────┬────────────────┼─────────────┬──────────┐
              ▼                        ▼                ▼             ▼          ▼
        ┌──────────┐         ┌──────────────────┐ ┌──────────┐ ┌────────┐  ┌────────┐
        │ assisted │         │   paybyphone     │ │ easypark │ │flowbird│  │  opngo │
        │ iMessage │         │  (httpx, OAuth)  │ │  (stub)  │ │ (stub) │  │ (stub) │
        └──────────┘         └──────────────────┘ └──────────┘ └────────┘  └────────┘
```

## Modules

| Module                        | Responsabilité                                    |
|-------------------------------|---------------------------------------------------|
| `boring.cli`                  | Entry point Typer pour toutes les commandes       |
| `boring.glue`                 | Orchestration : run loop + `process_trigger()`    |
| `boring.capture`              | Capture webcam OpenCV (interactive + auto)        |
| `boring.detect`               | YOLOv8 inference + `StreamTracker` anti-FP        |
| `boring.geofence`             | Point-in-polygon Lille (Shapely)                  |
| `boring.notify`               | Notifications macOS (osascript)                   |
| `boring.payment.base`         | Interface `PaymentProvider` + `ParkingSession`    |
| `boring.payment.assisted`     | Provider iMessage (rappel intelligent)            |
| `boring.payment.paybyphone`   | Client API PayByPhone (httpx, OAuth Bearer)       |
| `boring.payment.easypark`     | Stub (à reverser)                                 |
| `boring.payment.flowbird`     | Stub (à reverser)                                 |
| `boring.payment.opngo`        | Stub (API officielle à valider)                   |

## Contrats d'interface

### PaymentProvider (`boring/payment/base.py`)

Tous les clients de paiement implémentent :

```python
class PaymentProvider(ABC):
    name: str

    def login(self, username: str, password: str) -> None: ...
    def get_zone_id(self, lat: float, lon: float) -> str: ...
    def start_session(self, plate: str, location_id: str, minutes: int) -> ParkingSession: ...
    def get_active_session(self, plate: str) -> ParkingSession | None: ...
```

Le `PROVIDER_REGISTRY` dans `boring.payment` mappe le nom (`"paybyphone"`,
`"easypark"`, etc.) à la classe. Sélection au runtime via `PAYMENT_PROVIDER` (.env).

### StreamTracker (`boring/detect.py`)

Pattern : accumule N détections dans une fenêtre temporelle de M secondes,
ne déclenche qu'à partir du N-ème. Reset au premier "miss".

Évite le double-paiement sur un véhicule détecté pendant 1 frame isolée
(qui peut être une voiture random, un taxi, etc.).

### Cooldown (`boring/glue.py`)

`PaymentCooldown` : un seul paiement par fenêtre `COOLDOWN_MINUTES`. Empêche
de payer 12 fois si la même scan car repasse devant la caméra plusieurs fois.

Le cooldown s'enregistre **uniquement** sur paiement réussi (pas sur échec).
Permet de retenter immédiatement après un crash réseau.

## Décisions clés

### Pourquoi un mode "assisted" + un mode "auto"

- **Assisted (iMessage)** : ne fait pas de paiement réel automatique. Le système
  alerte l'utilisateur via iMessage avec un lien vers l'app. L'utilisateur valide
  manuellement. **Légalement défendable** ("outil de paiement optimisé") et
  shippable immédiatement.
- **Auto (API)** : déclenche le paiement directement via l'API du provider.
  **Pré-requis** : reverse-engineering du provider (cf. `scripts/parse_paybyphone_har.py`)
  + compte utilisateur configuré. Vraie automation.

Le toggle via `PAYMENT_MODE` permet de basculer sans rebuilder.

### Pourquoi YOLOv8n (vs autres modèles)

- Modèle léger (3 Mo), tourne en MPS sur Apple Silicon à 30+ FPS sur webcam Mac
- Stack ultralytics : training + inférence + export ONNX/CoreML/TFLite intégrés
- Baseline COCO inclut déjà la classe "car", utilisable avant fine-tune custom
- Adapté au déploiement embarqué (Raspberry Pi 5 + Coral USB, iPhone Neural Engine)

### Pourquoi `target_labels` paramétrable

- Mode baseline : `target_labels=("car",)` détecte toute voiture COCO
- Mode fine-tuned : `target_labels=("control_vehicle",)` une fois `best.pt` produit
- Switch sans modifier le code, juste un flag CLI / config

### Pourquoi un fallback GeoJSON hardcodé pour Lille

L'API OpenData MEL a migré en cours de route et aucune source live ne sert plus
les zones de stationnement payant proprement (cf. `scripts/download_lille_zones.py`
docstring). Le fallback bounding box du centre-ville débloque le MVP. À raffiner
quand MEL stabilisera sa nouvelle API geOrchestra.

## Flow paiement (mode auto)

```
1. detect.run_live_detection (5 fps)
   ├─ YOLO inference
   ├─ StreamTracker accumulate (3 frames in 2s window)
   └─ yield detections when threshold crossed

2. glue.process_trigger(payment, cooldown, lat, lon, ...)
   ├─ if not in_paid_zone : return None
   ├─ if not cooldown.allow() : return None
   ├─ zone_id = payment.get_zone_id(lat, lon)
   ├─ session = payment.start_session(plate, zone_id, duration)
   │   ├─ POST /parking/accounts/{id}/sessions
   │   └─ Bearer auth + X-Pbp-Version: 2
   ├─ cooldown.record()
   ├─ notify("Boring — payé", ...)
   └─ return session
```

## Flow paiement (mode assisted)

```
1. detect (idem)

2. glue.process_trigger(...)
   ├─ guards (idem)
   ├─ AssistedPayByPhone.start_session(...)
   │   ├─ build_deep_link(...)
   │   └─ send_imessage(recipient, "Boring — pense à payer X min...")
   ├─ cooldown.record()
   └─ return synthetic session

3. (Côté utilisateur, sur iPhone)
   ├─ Reçoit iMessage en ~1s
   ├─ Tap sur le lien → app PayByPhone s'ouvre
   └─ Saisit + valide manuellement (~10s)
```

## Points d'extension

- **Nouveau provider** : implémenter `PaymentProvider`, enregistrer dans
  `PROVIDER_REGISTRY`, ajouter ENV var, ajouter à `tests/test_multi_provider.py`
- **Nouvelle ville** : produire le GeoJSON des zones payantes, charger via
  `LilleParkingZones` (renommer en `ParkingZones` si on généralise)
- **Détection custom** : produire un dataset Roboflow, lancer `train_custom.py`,
  utiliser `--model models/best.pt --target <class>` dans `boring detect`
- **Nouveau canal d'alerte (mode assisted)** : push notif, SMS, Telegram —
  extraire `send_imessage()` derrière une interface `Notifier`

## Tests

- **Unitaires** (`tests/test_*.py`) : geofence, tracker, payment stubs, deep link
- **Intégration** (`tests/test_glue_integration.py`) : `process_trigger` end-to-end
  avec MockProvider + NotifyCollector

33+ tests, ~2s en local. CI sur chaque push (ruff + pytest).
