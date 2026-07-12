# Code audit

Date: 2026-07-12

## Verdict

Le repo est sain pour un prototype technique ambitieux: les domaines sont bien
separes, les gates de readiness sont nombreux, la CI couvre 441 tests, et les
chemins critiques ont des preuves locales reproductibles.

Le code n'est pas "trop abstrait"; il est plutot devenu tres defensif autour du
boitier terrain. Les vrais points de vigilance pour un CTO sont donc:

- `src/boring/evidence_pack.py` et `src/boring/production_readiness.py` sont
  volontairement stricts mais volumineux. Les refactorer demande des lots
  prudents avec tests de non-regression.
- `src/boring/cli.py` concentre beaucoup de commandes Typer. C'est acceptable
  pour un CLI unique, mais le prochain palier de maintenabilite serait de
  deplacer les commandes par domaine.
- les providers EasyPark, Flowbird et OPnGO restent des stubs. C'est explicite,
  mais il ne faut pas les presenter comme des integrations production.
- la readiness terrain reste bloquee par des artefacts reels: dataset YOLO,
  HAR PayByPhone, prototype Pi, burn-in 10h.

## Architecture actuelle

| Zone | Fichiers principaux | Role |
| --- | --- | --- |
| CLI | `src/boring/cli.py` | Commandes operateur, readiness, vision, autopay |
| Runtime box | `src/boring/runtime.py`, `src/boring/config.py` | Service headless, config, alertes, power saver |
| Detection | `src/boring/detect.py`, `src/boring/vision_eval.py`, `src/boring/vision_readiness.py` | Inference YOLO, evaluation, gate dataset/modele |
| Paiement | `src/boring/payment/*`, `src/boring/autopay_*` | Providers, readiness, smoke test paiement |
| Readiness terrain | `src/boring/production_readiness.py`, `src/boring/evidence_pack.py` | Gate final et pack de preuves |
| Hardware Pi | `deploy/pi/*`, `src/boring/*_readiness.py` | Installation, systemd, camera, reseau, power, position |
| Contestation | `src/boring/contest/*` | RAPO et contestation FPS |

## Nettoyages appliques

### PR #136 - Factor provider dry-run stubs

Changement: extraction de `src/boring/payment/stub.py`.

Impact:

- EasyPark, Flowbird et OPnGO partagent maintenant le meme lifecycle dry-run.
- Les fichiers providers ne contiennent plus chacun leur copie de
  `login/get_zone_id/start_session/get_active_session/stop_session`.
- Reduction nette: 146 lignes supprimees, 93 ajoutees.

Validation:

- `uv run ruff check src tests scripts`
- `uv run ruff format --check src tests scripts`
- `uv run pytest` -> 437 passed
- CI GitHub verte avant merge.

### PR #137 - Prune dead provider code

Changement: suppression de code mort evident.

Impact:

- suppression de `EasyParkAPIError` et `FlowbirdAPIError`, jamais references;
- simplification de `evidence_item_ok`, qui contenait une branche sans effet.
- Reduction nette: 20 lignes supprimees.

Validation:

- `uv run ruff check src tests scripts`
- `uv run ruff format --check src tests scripts`
- `uv run pytest` -> 437 passed
- CI GitHub verte avant merge.

### PR #139 - Extract readiness JSON helpers

Changement: extraction de `src/boring/readiness_json.py`.

Impact:

- `production_readiness.py` et `evidence_pack.py` partagent maintenant le parsing
  de timestamps et le calcul SHA-256;
- l'ancien parsing timestamp dupliqué a été supprimé;
- les gros fichiers readiness restent stricts, mais la première extraction est
  faite sans rewrite global.

Validation:

- `uv run ruff check src tests scripts`
- `uv run ruff format --check src tests scripts`
- `uv run pytest` -> 437 passed
- CI GitHub verte avant merge.

### PR #140 - Extract vision CLI commands

Changement: extraction de `src/boring/cli_vision.py`.

Impact:

- `vision-ready`, `vision-sources`, `vision-benchmark` et `vision-eval` sortent
  du CLI monolithique;
- `boring.cli:app` reste l'entrypoint public;
- les noms et l'ordre des commandes top-level sont conservés.

Validation:

- `uv run boring --help`
- `uv run ruff check src tests scripts`
- `uv run ruff format --check src tests scripts`
- `uv run pytest` -> 437 passed
- CI GitHub verte avant merge.

## Ce qui a ete audite

- etat Git/GitHub: `main` aligne avec `origin/main`;
- baseline qualite: ruff, format, pytest;
- structure complete du repo via `rg --files`;
- taille des modules via `wc -l`;
- recherche de stubs, TODO, NotImplemented, branches mortes et symboles publics
  peu references;
- inspection ciblee des providers, du CLI, de `evidence_pack.py` et de
  `production_readiness.py`.

## Dette restante

### 1. Fichiers readiness tres gros

`production_readiness.py` (~1824 lignes) et `evidence_pack.py` (~2114 lignes)
sont les deux fichiers les plus lourds. Ils sont bien testes, mais leur taille
augmente le cout de revue.

Recommandation:

- extraire progressivement des helpers communs de lecture JSON, timestamp,
  hash, details d'erreur;
- ne pas faire un gros rewrite global;
- garder chaque extraction sous PR separee avec `tests/test_production_readiness.py`
  et `tests/test_evidence_pack.py` en filet de securite.

### 2. CLI monolithique

`cli.py` depasse 1100 lignes parce qu'il regroupe toutes les commandes.

Recommandation:

- prochain refactor utile: `cli_readiness.py`, `cli_vision.py`, `cli_autopay.py`;
- conserver `boring.cli:app` comme entrypoint public;
- migrer une famille de commandes par PR.

### 3. Stubs providers

Les stubs sont maintenant factorises, mais ils restent volontairement non
production.

Recommandation:

- garder EasyPark/Flowbird/OPnGO clairement marques comme stubs;
- ne promouvoir un provider que lorsqu'un HAR ou une doc API valide couvre
  login, zone, start, active session et stop.

### 4. Documentation d'architecture

`ARCHITECTURE.md` decrit encore l'architecture historique. Il reste utile mais
doit etre maintenu avec les nouveaux modules readiness/evidence.

Recommandation:

- le traiter comme document d'onboarding technique;
- le garder court, et renvoyer les details terrain vers `docs/BOX.md`.

## Prochaines PRs utiles

1. Extraire les commandes Typer autopay dans `cli_autopay.py`.
2. Extraire les commandes Typer readiness/runtime dans `cli_readiness.py`.
3. Extraire de nouveaux helpers JSON prudemment depuis `production_readiness.py`
   et `evidence_pack.py`.
4. Transformer `code-audit` en sortie JSON optionnelle si on veut l'intégrer à CI.

## Decision

Le repo est propre et credible pour un CTO si on le presente comme un prototype
boitier avance avec gates terrain stricts. Il ne faut pas pretendre que les
integrations terrain sont terminees sans dataset, HAR et prototype Pi reels.
