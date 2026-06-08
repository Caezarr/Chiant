# Changelog

Tous les changements notables de ce projet sont documentés ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Added
- Scaffolding multi-provider : stubs `EasyParkClient`, `FlowbirdClient`, `OPnGOClient`
- Registry `PROVIDER_REGISTRY` + helper `get_provider_class()`
- Variable `PAYMENT_PROVIDER` dans `.env` pour sélectionner le client API
- Pre-commit hooks : ruff format/check, pytest fast, hygiène fichiers
- SECURITY.md (politique disclosure)
- ARCHITECTURE.md (à venir)
- Tests multi-provider (8 nouveaux)
- `boring.payment.base` : méthode `stop_session(session_id)` sur l'interface `PaymentProvider` (non-abstract, lève `NotImplementedError` par défaut)
- `boring.payment.paybyphone` : `_ensure_token()` — auto-vérification d'expiry 60s avant chaque appel réseau
- `boring.payment.paybyphone` : `stop_session()` — DELETE sur l'endpoint sessions
- `boring.payment.paybyphone` : retry réseau automatique via `httpx.HTTPTransport(retries=3)`
- `boring.payment.easypark/flowbird/opngo` : `stop_session()` avec `NotImplementedError` propre
- `boring.contest.rapo` : génération de courrier RAPO via Claude API (`claude-opus-4-8`) en mode `use_ai=True, dry_run=False`
- CLI `contest-fps` : options `--ai/--no-ai`, `--live`, `--evidence` (pièces justificatives)
- Dépendance `anthropic>=0.40` ajoutée
- Dataset `datasets/baseline/` : 57 images LAPI scrapées via DuckDuckGo (scraper baseline)

### Changed
- `make_payment_provider()` route entre `assisted` (iMessage) et tous les
  clients API du registry selon `PAYMENT_MODE` + `PAYMENT_PROVIDER`

## [0.1.0] — 2026-05-25

### Added
- Pipeline détection live YOLOv8 + tracker anti-faux-positif
- Geofence Lille (fallback bounding box centre-ville)
- Client PayByPhone (squelette httpx, OAuth Bearer, endpoints itsff)
- Provider assisté via iMessage (osascript Messages.app)
- CLI typer : `boring version`, `capture`, `detect`, `run`, `pay-now`
- Notifications macOS
- Scripts utilitaires : `download_lille_zones.py`, `prepare_dataset.py`,
  `train_custom.py`, `paybyphone_capture.py` (mitmproxy), `parse_paybyphone_har.py`
- Tests pytest : 16/16 passants
- CI GitHub Actions (ruff + pytest)
- LICENSE Apache 2.0
- HUMAN-TODO.md : actions humaines clairement séquencées

[Unreleased]: https://github.com/Caezarr/Chiant/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Caezarr/Chiant/releases/tag/v0.1.0
