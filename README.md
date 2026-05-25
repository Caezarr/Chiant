# Boring · `Chiant`

> **Boring** — assistant de paiement optimisé du stationnement urbain.
> Premier produit d'une suite anti-friction administrative française.
>
> *Le repo est public sous le codename `Chiant` jusqu'au dépôt INPI de la marque.*

[![CI](https://github.com/Caezarr/Chiant/actions/workflows/ci.yml/badge.svg)](https://github.com/Caezarr/Chiant/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Status: pre-alpha](https://img.shields.io/badge/Status-pre--alpha-orange)](#statut)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](pyproject.toml)

## Pitch

Tu te gares en ville, tu oublies de payer ton stationnement, tu te ramasses un FPS de 35€. Multiplé par dix par an = ~400€ d'amendes administratives évitables. Et selon le régulateur néerlandais, **500 000 FPS / an sont injustifiés** (capteurs LAPI mal calibrés, scan d'une plaque déjà payée, etc.).

Boring détecte visuellement les véhicules de contrôle automatisé qui s'approchent, et soit te rappelle d'urgence de payer ta session (mode `assisted`), soit la déclenche directement via l'API du provider (mode `auto`). Tu paies le minimum légal (~30 cts pour 15 min), tu ne paies jamais un FPS injustifié.

👉 **Si tu maintiens ce repo, lis [`HUMAN-TODO.md`](HUMAN-TODO.md)** pour savoir quoi faire concrètement.

## Quick start (Mac, Apple Silicon)

```bash
git clone https://github.com/Caezarr/Chiant.git
cd Chiant
cp .env.example .env          # → renseigne ASSISTED_IMESSAGE_RECIPIENT au minimum
make dev                      # uv sync + outils dev
make test                     # 33+ tests doivent passer
make zones                    # télécharge / met à jour les zones Lille
uv run boring pay-now --plate AB-123-CD --duration 15    # smoke test paiement
```

## Statut

**Pre-alpha**. MVP en construction. Pas pour usage réel pour l'instant.

### Ce qui marche ✅

- Pipeline détection live YOLOv8 + tracker anti-faux-positif (baseline COCO `car`)
- Geofence Lille fonctionnelle (fallback bounding box centre-ville)
- Mode paiement `assisted` via iMessage (rappel intelligent → tu valides en 1 tap)
- Multi-provider scaffolding : PayByPhone (réel), EasyPark / Flowbird / OPnGO (stubs)
- CLI complète : `boring capture / detect / run / pay-now`
- Tests pytest, CI GitHub Actions, pre-commit hooks

### Ce qui manque ⏳

- Modèle custom `control_vehicle` (besoin captation terrain — cf. HUMAN-TODO #1-3)
- Reverse PayByPhone validé (besoin HAR — cf. HUMAN-TODO #4)
- Clients EasyPark / Flowbird / OPnGO implémentés
- Vraies zones Lille (API MEL en migration côté serveur)

## Architecture (en 1 paragraphe)

`boring.cli` parse les commandes → `boring.glue` orchestre → `boring.detect` (YOLO) émet des triggers → `boring.geofence` (Shapely) filtre par zone → `boring.glue.process_trigger` appelle `boring.payment.<provider>` → `boring.notify` envoie une notif macOS. Tout est testable indépendamment.

Détail dans [ARCHITECTURE.md](ARCHITECTURE.md).

## Modes de paiement

| Mode       | Risque légal | Latence | Friction user      | Dispo  |
|------------|--------------|---------|--------------------|--------|
| `assisted` | Nul          | ~4 s    | 1 tap iPhone       | ✅     |
| `auto`     | Zone grise   | < 1 s   | Aucune             | ⏳ HAR |

Toggle via `PAYMENT_MODE=assisted|auto` dans `.env`.

## Multi-provider

Le `PROVIDER_REGISTRY` permet de basculer le client API au runtime :

```bash
PAYMENT_PROVIDER=paybyphone   # défaut (impl. la plus avancée)
PAYMENT_PROVIDER=easypark     # stub
PAYMENT_PROVIDER=flowbird     # stub
PAYMENT_PROVIDER=opngo        # stub
```

Tous implémentent `PaymentProvider` (interface dans `src/boring/payment/base.py`).
Pour ajouter un provider, voir [ARCHITECTURE.md § Points d'extension](ARCHITECTURE.md#points-dextension).

## Roadmap

- [x] **v0.1** — MVP scaffolding (vision + payment abstraction + assisted iMessage)
- [ ] **v0.2** — Modèle custom `control_vehicle` fine-tuné sur dataset Lille
- [ ] **v0.3** — Client PayByPhone validé via HAR, mode `auto` actif
- [ ] **v0.4** — Multi-provider live (EasyPark + OPnGO)
- [ ] **v0.5** — Boîtier hardware Raspberry Pi 5 documenté
- [ ] **v1.0** — Documentation utilisateur complète, dépôt INPI Boring sécurisé

## Compatibilité

- macOS Apple Silicon (M1+) — cible principale dev
- Linux x86 — fonctionne, sauf notifs macOS (fallback console)
- Raspberry Pi 5 — cible de déploiement (v0.5)

## Différenciation vs prior art

Haloban Lab (Paris) a démontré en mai 2026 un système équivalent (Pi + 2 webcams + YOLO baseline). Edge de Boring :

1. Modèle **custom `control_vehicle`** (vs YOLO COCO générique → ils trigger sur toute voiture qui passe)
2. **Lille first** (eux Paris-only)
3. **Boîtier hardware fini** vendu pré-flashé (eux : DIY)
4. **Framing légalement défendable** : "outil de paiement optimisé", pas "ANTI PV"
5. **Multi-provider** : PayByPhone + EasyPark + OPnGO + Flowbird (vs PayByPhone-only)

## Contribuer

- Issues : utilise les templates dans `.github/ISSUE_TEMPLATE/`
- PRs : checklist dans `.github/pull_request_template.md`
- Setup dev : `make dev && pre-commit install`
- Tests : `make test` (33+ tests, doit passer avant commit)

## Sécurité

Vulnérabilités : voir [SECURITY.md](SECURITY.md). En court : `gabriel@meetwonka.com` avec préfixe `[SECURITY]`.

## Licence

[Apache 2.0](LICENSE). Le code est libre. La marque commerciale "Boring" est réservée à Caezarr / Gabriel.

## Avertissement juridique

L'objectif explicite de Boring est de **faciliter le paiement du stationnement**, pas de l'éviter. Le minimum payé est toujours > 0. Précédent à ne pas reproduire : [Parkeerwekker (NL)](https://blog.iusmentis.com/2022/06/02/oh-ja-dat-parkeerwekker-bestond-dus-nog-maar-in-hoger-beroep-niet-meer/) interdit en appel 2022 pour framing "anti-contrôle". Boring ne fait pas ça.
