# Boring

> Assistant de paiement intelligent du stationnement urbain.
> Détection visuelle des véhicules de contrôle → paiement programmatique du minimum légal.

Premier produit de **Boring** — anti-friction administrative française.

## Statut

Pre-alpha. MVP en construction. Aucune utilisation réelle recommandée pour l'instant — l'intégration paiement est stubée en `dry_run=True`.

👉 **Si tu maintiens ce repo et veux savoir quoi faire ensuite, lis [`HUMAN-TODO.md`](HUMAN-TODO.md).**

## Quick start (Mac, Apple Silicon)

```bash
make dev                # installe deps + outils dev (mitmproxy, ruff)
make zones              # télécharge les zones payantes Lille (data.gouv.fr)
make capture            # ouvre la webcam pour tester
make detect             # détection live (baseline COCO 'car' avant fine-tune)
make run                # pipeline end-to-end (paiement stubé pour l'instant)
```

Copie `.env.example` vers `.env` et renseigne tes vraies valeurs avant `make run`.

## Architecture

```
[ Webcam ] → [ YOLOv8 detect ] → [ StreamTracker ]
                                       ↓ (N frames consécutives)
                                  [ Geofence Lille ]
                                       ↓ (en zone payante ?)
                                  [ Cooldown ]
                                       ↓ (pas payé dans les 10 min ?)
                                  [ PayByPhone API ]
                                       ↓
                                  [ Notif macOS ]
```

### Modules

| Module                       | Rôle                                                              |
|------------------------------|-------------------------------------------------------------------|
| `boring.capture`             | Flux webcam OpenCV, capture interactive / auto                    |
| `boring.detect`              | Inférence YOLOv8 + tracker anti-faux-positif                      |
| `boring.geofence`            | Point-in-polygon Lille (GeoJSON data.gouv.fr)                     |
| `boring.payment.base`        | Interface abstraite `PaymentProvider`                             |
| `boring.payment.paybyphone`  | Client PayByPhone — **STUB**, reverse à venir Phase 5             |
| `boring.notify`              | Notifications macOS (osascript)                                   |
| `boring.glue`                | Orchestration end-to-end + cooldown                               |
| `boring.cli`                 | CLI `boring …`                                                    |

## Roadmap MVP

- [x] **Phase 1** — Setup repo + capture webcam Mac
- [ ] **Phase 2** — Captation terrain Lille (500 images annotées via Roboflow)
- [ ] **Phase 3** — Fine-tune YOLOv8n sur classe `scan_car`
- [ ] **Phase 4** — Tracker anti-FP en condition réelle
- [ ] **Phase 5** — Reverse API PayByPhone via mitmproxy
- [ ] **Phase 6** — Démo end-to-end live

## Captation terrain (Phase 2)

1. Filme avec ton iPhone (4K, 30fps) depuis un café ou ta voiture stationnée
2. Spots Lille : **Gambetta**, **Vauban-Esquermes**, **Vieux-Lille rue Royale**, **Pierre Legrand (Fives)**
3. Horaires de patrouille typiques : mar-jeu 9h-12h
4. Mets les `.mov` dans `datasets/raw/`
5. `make prepare` → échantillonne 1 frame/seconde dans `datasets/extracted/`
6. Upload sur [Roboflow](https://roboflow.com), annote 1 classe `scan_car`, exporte en YOLOv8

## Différenciation (vs prior art FR)

Haloban Lab a montré en mai 2026 un système équivalent (Pi + 2 webcams + YOLO COCO baseline + paiement 15 min). Edge concurrentiel de Boring :

1. **Modèle custom `scan_car`** (eux utilisent COCO `car` générique → ils paient à chaque voiture qui passe)
2. **Lille first** (eux : Paris)
3. **Boîtier hardware vendu pré-flashé** (eux : DIY only)
4. **Framing juridique défendable** : "outil de paiement optimisé", pas "ANTI PV" / "anti Hidalgo"

## Reverse PayByPhone (Phase 5)

Pipeline :
1. `uv run mitmproxy` sur ton Mac (port 8080)
2. iPhone : Réglages Wi-Fi → proxy manuel → ton IP locale + 8080
3. Va sur `mitm.it` depuis Safari iPhone → installe le certificat CA
4. Ouvre l'app PayByPhone, login, lance une session 15 min
5. Capture les requêtes dans mitmproxy → mappe endpoints, headers, payloads

Référence partielle : [itsff/PayByPhone-api-docs](https://github.com/itsff/PayByPhone-api-docs).

## Licence

Apache 2.0 prévu pour le code. Dataset en CC-BY (annotations terrain). À sécuriser avant publication publique.

## Avertissement juridique

Précédent : [Parkeerwekker (NL)](https://blog.iusmentis.com/2022/06/02/oh-ja-dat-parkeerwekker-bestond-dus-nog-maar-in-hoger-beroep-niet-meer/) interdit en appel 2022. Le framing public **doit être** "outil de paiement optimisé du stationnement", jamais "anti-contrôle". Le minimum payé doit toujours être > 0.
