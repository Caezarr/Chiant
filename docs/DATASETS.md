# Computer vision dataset plan

Objectif : obtenir rapidement un modele `control_vehicle` sans dependre uniquement d'une captation manuelle a Lille.

## Sources gratuites utiles

Le catalogue versionne `data/vision_free_sources.json` garde les sources candidates lisibles par la CLI et par `vision-ready`. Pour l'afficher :

```bash
uv run boring vision-sources
```

| Source | Usage | Licence / risque | Action |
|---|---|---|---|
| Open Images V7 | Negatifs et vehicules generiques | Images avec annotations a grande echelle, verifier licence image par image | Telecharger classes `Car`, `Van`, `Truck`, `Bus` pour hard negatives |
| Mapillary / Mapillary Vistas | Scenes urbaines europeennes, angle street-level | Images Mapillary sous CC BY-SA; Vistas peut demander login/licence | Chercher rues Lille/Paris + vehicules municipaux visibles |
| BDD100K | Negatifs conduite jour/nuit/pluie | Dataset recherche conduite, verifier conditions avant usage commercial | Utiliser pour robustesse lumiere/meteo, pas pour label final |
| Roboflow Universe | Recherche de datasets "parking enforcement", "ANPR", "police car" | Chaque dataset a sa propre licence | Importer seulement datasets licence claire |
| YouTube / TikTok frames | Vehicules LAPI reels | Risque copyright eleve | A reserver pour validation interne, pas train commercial |
| Presse / collectivites | Photos officielles voitures LAPI | Licence variable | Chercher pages avec licence ouverte, sinon demander autorisation |

Sources verifiees en juillet 2026 :

- Open Images V7 annonce 15,851,536 bounding boxes sur 600 classes : https://storage.googleapis.com/openimages/web/index.html
- Roboflow Universe annonce 1B+ images et 1M+ datasets : https://universe.roboflow.com/
- BDD100K est decrit comme 100K videos de conduite avec diversite meteo/geographique : https://arxiv.org/abs/1805.04687
- Mapillary est une source street-level crowdsourced; verifier les conditions exactes avant usage produit : https://www.mapillary.com/

## Strategie dataset

### Phase 1 — baseline sans filmer

1. Constituer 2 000-5 000 negatives propres :
   - voitures normales
   - utilitaires blancs
   - voitures avec camera/toit
   - bus/taxis/police/ambulances
2. Scraper/importer 200-500 positifs probables :
   - requetes FR : `voiture LAPI`, `voiture radar stationnement`, `vehicule controle stationnement`, `scan car`
   - requetes EN/NL : `parking enforcement vehicle`, `ANPR parking car`, `scan car parking`
3. Annoter strictement `control_vehicle`; tout doute devient negative ou `ignore`.

Commandes repo :

```bash
make scrape-baseline   # positifs probables: datasets/baseline/positives
make scrape-negatives  # hard negatives: datasets/baseline/negatives
make import-openimages # hard negatives Open Images depuis CSV locaux
make vision-ready      # audit local dataset/modele avant boitier
```

Pour Open Images, telecharge localement les CSV officiels dans `datasets/openimages/` :

- `class-descriptions-boxable.csv`
- `train-annotations-bbox.csv` ou `validation-annotations-bbox.csv`

Puis lance par exemple :

```bash
uv run python scripts/import_openimages_manifest.py \
  --descriptions datasets/openimages/class-descriptions-boxable.csv \
  --annotations datasets/openimages/train-annotations-bbox.csv \
  --classes Car,Van,Truck,Bus \
  --limit 500
```

Le script ajoute des entrees `open-images` au manifest et ecrit `datasets/baseline/openimages-download-list.txt`. Il ne telecharge pas les fichiers tout seul; tu peux ensuite utiliser cette liste avec `curl`, `wget` ou un outil de dataset maison. Ces images servent surtout de hard negatives propres, pas de positifs `control_vehicle`.

Chaque image telechargee ou importee est tracee dans `datasets/baseline/manifest.jsonl` avec :

- URL source
- query
- profil (`positives` / `negatives`)
- label hint
- hash perceptuel
- licence `unknown-review-before-training`
- statut `license_reviewed=false`

Ce manifeste sert a filtrer avant annotation et a ne pas melanger aveuglement des images sans licence claire dans un dataset commercial. Les images scrapees DuckDuckGo sont donc des candidates. Les lignes Open Images importees sont marquees `license_status=open-images` et `license_reviewed=true`, mais leur usage reste a cantonner aux conditions Open Images. Pour qu'une image web candidate compte dans le gate prod, il faut la revoir et mettre par exemple :

```json
{"license_reviewed": true, "license_status": "cc-by", "license_note": "source page says CC BY 4.0"}
```

Statuts acceptes par `vision-ready` : `owned`, `public-domain`, `cc0`, `cc-by`, `cc-by-sa`, `open-images`, `roboflow-allowed`, `approved`.

## Audit readiness

Avant de mettre `DETECTION_MODEL=models/best.pt` sur le boitier :

```bash
uv run boring vision-ready
```

La commande verifie :

- `data/vision_free_sources.json` : au moins deux sources positives candidates et deux sources negatives candidates gratuites, sans compter les sources reservees a la validation interne.
- `datasets/baseline/manifest.jsonl` : volume minimal de positifs probables et hard negatives gratuits.
- revue licence : toutes les lignes du manifest doivent etre approuvees avant un gate prod.
- `datasets/control_vehicle_v1/data.yaml` : export YOLOv8 present, classe `control_vehicle`, images train/valid suffisantes.
- `models/best.pt` : modele fine-tune present et non vide.

Pour travailler sur un dataset candidat sans pretendre qu'il est utilisable en prod :

```bash
uv run boring vision-ready --allow-unreviewed-sources
```

Pour preparer un Pi 4/5 avec runtime edge :

```bash
uv run boring vision-ready --require-edge-export
uv run boring vision-eval --dataset datasets/control_vehicle_v1 --model models/best.pt --split valid --frame-interval 1 --output reports/vision-eval.json
uv run boring vision-benchmark --model models/best.pt --device cpu --frames 120 --min-fps 2.0
```

Dans ce mode, le check exige aussi `models/best.onnx` ou `models/best.tflite`. `vision-eval` lit le split YOLO, lance le modele, calcule recall, precision, faux positifs par heure, nombre de frames evaluees et images invalides, puis ecrit `reports/vision-eval.json` avec `generated_at`. `vision-benchmark` mesure ensuite le FPS reel d'inference sur le hardware cible et ecrit `reports/vision-benchmark.json` avec `generated_at`. Sur Pi 4, viser au moins 1 FPS; sur Pi 5, viser 2 FPS ou plus avant beta terrain.

### Phase 2 — terrain minimum

Meme avec sources gratuites, il faut un petit set local :

- 300-500 images Lille / Hauts-de-France
- angles proches du boitier reel
- matin, midi, soir, pluie, reflets pare-brise

La captation terrain sert surtout a reduire le domain gap.

### Phase 3 — validation

Metriques minimales avant demo publique :

- Recall cible > 90% sur vehicules de controle visibles a 15-30m
- False positive < 1 par heure garee en rue passante
- Aucun autopaiement sur vehicule normal dans un test continu de 10h
- `vision-ready --require-edge-export` passe avant installation Pi.
- `vision-eval` produit un rapport avec `frames_evaluated > 0`, `invalid_images=0`, recall >= 90%, faux positifs <= 1/h.
- `vision-benchmark` passe sur le Pi cible.
- `reports/vision-eval.json` passe avant `box-ready`.

Format attendu par le gate final :

```json
{
  "model_path": "models/best.pt",
  "dataset_id": "field-pi5-daylight-v1",
  "recall": 0.93,
  "precision": 0.98,
  "false_positive_per_hour": 0.5,
  "evaluated_hours": 3.0,
  "frames_evaluated": 10800,
  "true_positives": 93,
  "false_positives": 1,
  "false_negatives": 7,
  "invalid_images": 0,
  "min_recall": 0.9,
  "max_false_positive_per_hour": 1.0,
  "passed": true
}
```

Si la precision n'est pas atteinte, rester en mode `assisted` ou demander confirmation user avant paiement.
