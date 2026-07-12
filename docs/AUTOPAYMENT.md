# Autopaiement

Objectif : declencher une session minimale de stationnement quand le boitier detecte un vehicule de controle.

## Etat actuel

Le code supporte deux modes :

- `assisted` : iMessage / lien vers PayByPhone, validation humaine.
- `auto` : provider API, mais bloque en `PAYMENT_DRY_RUN=true` tant que le HAR reel n'a pas valide les endpoints.

Pour autoriser un vrai paiement :

```bash
PAYMENT_MODE=auto
PAYMENT_PROVIDER=paybyphone
PAYMENT_DRY_RUN=false
MAX_SESSION_AMOUNT_CENTS=500
MAX_DAILY_AMOUNT_CENTS=1500
PAYBYPHONE_USERNAME=...
PAYBYPHONE_PASSWORD=...
PAYBYPHONE_API_BASE=...
PAYBYPHONE_AUTH_URL=...
PAYBYPHONE_CLIENT_ID=...
PAYBYPHONE_RATE_OPTION_ID=...
PAYBYPHONE_PAYMENT_METHOD_ID=...
PAYBYPHONE_LOCATION_ID=...     # optionnel si lookup GPS ambigu
```

## Procedure PayByPhone

1. Capturer un HAR web complet : login, creation session 15 min, verification session active, stop session.
2. Lancer :

```bash
uv run python scripts/parse_paybyphone_har.py scripts/pbp.har
uv run boring setup-paybyphone
uv run boring autopay-ready
uv run boring autopay-smoke --yes --output reports/autopay-smoke.json
```

3. Verifier que le HAR a bien extrait :
   - `PAYBYPHONE_RATE_OPTION_ID`
   - `PAYBYPHONE_PAYMENT_METHOD_ID`
   - format exact `locationId`
   - flow critique `auth`, `location_lookup`, `session_start`, `active_session_check`, `session_stop`
4. Tester avec `PAYMENT_DRY_RUN=false` sur une zone reelle et une duree minimale via `autopay-smoke`. Si la resolution GPS PayByPhone retourne plusieurs zones, configurer `PAYBYPHONE_LOCATION_ID` au lieu de laisser le client choisir. Lancer ce smoke apres la config finale: `box-ready` compare le rapport a `PAYMENT_PROVIDER`, `DEFAULT_VEHICLE_PLATE`, et `PAYBYPHONE_LOCATION_ID` quand elle est forcee.
5. Verifier via `uv run boring status --plate ...` si `--no-stop-after` a ete utilise.
6. Garder `reports/autopay-smoke.json` pour `box-ready`.

## Audit readiness

Avant de lancer un paiement reel, executer :

```bash
uv run boring autopay-ready
```

La commande ecrit `reports/autopay-readiness.json` et verifie localement :

- `PAYMENT_MODE=auto`
- `PAYMENT_PROVIDER=paybyphone`
- `PAYMENT_DRY_RUN=false`
- plaque configuree, duree, cooldown et plafonds financiers coherents
- credentials PayByPhone presents
- hints HAR presents (`API_BASE`, `AUTH_URL`, `CLIENT_ID`, `RATE_OPTION_ID`, `PAYMENT_METHOD_ID`)
- `PAYBYPHONE_LOCATION_ID` optionnel pour forcer une zone connue si la resolution GPS est ambigue
- position/geofence disponible
- `scripts/paybyphone_endpoints.json` present avec `config_hints`
- flow HAR critique complet : auth, resolution zone, start session, session active, stop session

Pour une repetition sans risque avant de basculer :

```bash
uv run boring autopay-ready --allow-dry-run
```

Cette variante n'echoue pas sur `PAYMENT_DRY_RUN=true`, mais tous les autres checks restent actifs.

## Smoke reel

Avant `box-ready` en mode prod :

```bash
uv run boring autopay-smoke --yes --output reports/autopay-smoke.json
```

Cette commande refuse de tourner sans `--yes`, refuse `PAYMENT_DRY_RUN=true`, verifie qu'aucune session n'est deja active pour la plaque, demarre une session minimale, re-verifie qu'elle est active, appelle `stop_session()`, puis verifie que la session n'est plus active. Le rapport doit contenir `passed=true`, `dry_run=false`, `active_session_verified=true`, `stopped=true`, `stop_verified=true` et un `amount_cents` positif inferieur ou egal a `MAX_SESSION_AMOUNT_CENTS`.

## Gardes de securite

Le paiement reel ne doit jamais partir si :

- `BOX_REQUIRE_GEOFENCE=true` et position absente
- hors zone payante
- session active deja presente sur la plaque
- cooldown actif
- plafond session depasse
- plafond journalier deja atteint ou depasse apres session
- batterie critique (`payment_skipped_battery_critical`)
- provider retourne une zone ambigue sans `PAYBYPHONE_LOCATION_ID`

Avant beta, `process_trigger` doit verifier `get_active_session()` avant `start_session()`.
Avant paiement reel, `autopay-ready` doit passer, puis `autopay-smoke` doit produire `reports/autopay-smoke.json`.

`MAX_SESSION_AMOUNT_CENTS` limite une session individuelle. `MAX_DAILY_AMOUNT_CENTS` limite le total journalier persistant dans `BOX_STATE_PATH`; le compteur survit donc a un reboot systemd. Si le provider retourne une session au-dessus du plafond, le runtime tente `stop_session()` immediatement et notifie l'utilisateur.

## Contrat produit

Le boitier ne doit pas etre vendu comme "anti-controle". Le wording reste : paiement minimal automatise du stationnement quand un controle est detecte. Le paiement est toujours > 0 et journalise.
