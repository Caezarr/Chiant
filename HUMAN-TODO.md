# HUMAN-TODO — Ce que toi (Gabriel) tu dois faire

> Tout le reste est ou sera automatisé côté code.
> Chaque étape débloque la suivante. Si tu en sautes une, je peux pas avancer.

---

## 🤖 Fait automatiquement (session 08/06/2026)
- [x] Token auto-refresh + retry réseau sur PayByPhoneClient
- [x] `stop_session()` sur toute l'interface de paiement
- [x] Courrier RAPO généré par Claude API (`boring contest-fps --live`)
- [x] CLI `--evidence`, `--ai`, `--live` sur `contest-fps`
- [x] `boring status` — vérifie la session active
- [x] `boring scrape` — lance le scraper baseline depuis la CLI
- [x] `boring setup-paybyphone` — configure `.env` depuis l'export HAR
- [x] HAR parser amélioré : extrait `config_hints` (base_url, auth_url, client_id, rate_option_id)
- [x] 57 images LAPI scrapées → `datasets/baseline/` (prêt pour Roboflow)
- [x] 5 PRs Dependabot mergées (pillow, typer, rich, imagehash, ddgs)
- [x] `datasets/` + `runs/` ajoutés au `.gitignore`

---

## ✅ Déjà fait

- [x] Repo initialisé, code MVP scaffolding poussé sur GitHub
- [x] Geofence Lille fonctionnelle (fallback hardcodé)
- [x] YOLOv8n baseline chargé, détection live OK
- [x] Stub paiement derrière interface abstraite

---

## ⏳ Action #1 — Captation vidéo Lille (1-2 weekends)

**Durée** : 2× sessions de ~1h
**Sortie attendue** : ~30 min de footage utilisable

### Comment

1. Prends ton iPhone, mode vidéo **4K à 30fps**
2. Va te poster discrètement à un ou plusieurs spots à fort trafic de véhicules de contrôle automatisé :
   - **Gambetta** (autour du métro)
   - **Vauban-Esquermes**
   - **Vieux-Lille** rue Royale / Place du Lion d'Or
   - **Pierre Legrand** (Fives)
3. Horaires les plus productifs : **mardi-jeudi 9h-12h**
4. Tu films la rue depuis un café, ta voiture, ou en marchant. Garde un cadre stable, le véhicule cible doit faire au moins 20% de la hauteur de l'image quand il passe.
5. Tu rentres chez toi, tu mets les fichiers `.mov` ou `.mp4` dans :
   ```
   /Users/gabriel/Desktop/GR/boring/datasets/raw/
   ```
6. Tu lances :
   ```bash
   cd /Users/gabriel/Desktop/GR/boring
   make prepare
   ```
   → ça extrait automatiquement 1 frame/seconde de chaque vidéo dans `datasets/extracted/`

### Comment savoir que c'est bon

Vérifie que `datasets/extracted/` contient **au moins 300 images** dont une bonne partie montre clairement un véhicule de contrôle. 500+ c'est mieux.

---

## ⏳ Action #2 — Annotation sur Roboflow (1 soirée)

**Durée** : 1h-2h (selon le nombre d'images)
**Sortie attendue** : un dataset annoté téléchargé localement

### Comment

1. Crée un compte gratuit sur https://roboflow.com
2. Crée un projet "Object Detection", classe unique : **`control_vehicle`**
3. Upload tout le dossier `datasets/extracted/`
4. Annote (boîte rectangulaire autour de chaque véhicule de contrôle visible). Outils utiles dans Roboflow :
   - **Label Assist** (IA pré-annote, tu corriges)
   - Raccourcis clavier : W (créer box), 1-9 (classe), N (image suivante)
5. Quand tu as ≥300 annotations : Generate → Augmentations standard (flip horizontal, +/-15° rotation, exposition ±20%) → Generate Dataset
6. Export → Format **YOLOv8** → Download zip
7. Décompresse dans `datasets/control_vehicle_v1/` (doit contenir `data.yaml`, `train/`, `valid/`, `test/`)

### Comment savoir que c'est bon

```bash
ls datasets/control_vehicle_v1/data.yaml  # doit exister
```

---

## ⏳ Action #3 — Lancer le training (1 commande, ~30 min)

**Durée** : 30-60 min sur ton M-series Mac
**Sortie attendue** : `models/best.pt` (le modèle fine-tuné)

```bash
cd /Users/gabriel/Desktop/GR/boring
uv run python scripts/train_custom.py --data datasets/control_vehicle_v1/data.yaml
```

Tu laisses tourner. À la fin, le script copie automatiquement le meilleur modèle dans `models/best.pt`.

### Test rapide

```bash
uv run boring detect --model models/best.pt --target control_vehicle
```

Pointe ta webcam vers une fenêtre où passe le bon type de véhicule → tu dois voir un cadre rouge "TRIGGER" après 3 frames consécutives.

---

## ⏳ Action #4 — Capture HAR du paiement web (~10 min)

**Durée** : 10 min
**Sortie attendue** : `scripts/paybyphone_endpoints.json` (à m'envoyer)

> Tu peux faire cette étape **dès maintenant**, en parallèle des actions 1-3.
> C'est la plus rapide pour débloquer le paiement automatique réel.

### Comment

1. Ouvre **https://m.paybyphone.fr** dans **Safari** (Mac) ou Chrome.

2. Ouvre les DevTools :
   - **Safari** : Préférences > Avancé > coche "Afficher Développement" > Développement > "Afficher l'inspecteur Web"
   - **Chrome** : Cmd-Option-J

3. Onglet **Network/Réseau** :
   - Coche "Preserve log" / "Conserver le journal"
   - Vide la liste (icône 🚫)

4. Sur le site PayByPhone, dans cet ordre :
   - **Login** avec ton compte
   - Renseigne ta **plaque** si pas déjà fait
   - **Démarre une session de stationnement** : 15 minutes, à un endroit réel de Lille (zone payante)
   - Vérifie qu'elle apparaît bien comme active dans l'app
   - **Stoppe la session** (pour pas payer 30 cts pour rien — et pour capturer le flow d'arrêt aussi)

5. Dans Network DevTools :
   - **Safari** : clic droit dans la liste → "Exporter HAR" → enregistre dans `/Users/gabriel/Desktop/GR/boring/scripts/pbp.har`
   - **Chrome** : clic droit → "Save all as HAR with content" → même chemin

6. Lance le parseur :
   ```bash
   cd /Users/gabriel/Desktop/GR/boring
   uv run python scripts/parse_paybyphone_har.py scripts/pbp.har
   ```
   → produit `scripts/paybyphone_endpoints.json` avec **credentials et tokens automatiquement masqués**.

7. **Envoie-moi `scripts/paybyphone_endpoints.json`** (drag-drop dans le chat).
   Je code le client réel et tu pourras lancer `boring pay-now` en mode `PAYMENT_MODE=auto` pour un vrai paiement.

### Test boîtier après intégration

Quand les variables PayByPhone sont en place :

```bash
PAYMENT_MODE=auto PAYMENT_DRY_RUN=false uv run boring box-doctor
PAYMENT_MODE=auto PAYMENT_DRY_RUN=false uv run boring pay-now --plate AB-123-CD --duration 15
```

Le vrai service headless se lance avec :

```bash
uv run boring box-run
```

Voir aussi [docs/BOX.md](docs/BOX.md) et [docs/AUTOPAYMENT.md](docs/AUTOPAYMENT.md).

### Si tu veux faire la version mobile à la place (1h)

Pour capturer l'app iOS native (vs le web), garde l'option `scripts/paybyphone_capture.py` + mitmproxy.
Moins recommandé : plus de friction (installer cert iOS, configurer proxy Wi-Fi), même résultat fonctionnel.

---

## ⏳ Action #5 (parallèle, hors code) — Sécuriser le naming

À faire **avant** toute communication publique sur la marque Boring :

1. Recherche sur https://data.inpi.fr/recherche : "Boring" + classes 35, 38, 42
2. Si libre, dépôt INPI classes 35/38/42 (~250€) — évite les classes infrastructure/tunnels où The Boring Company (Musk) est protégée
3. Achète **boring.fr** et un .com fallback type **boring-app.com** ou **getboring.com**
4. Repo public reste `Chiant` comme codename tant que le dépôt n'est pas confirmé

---

## Ce que je fais pendant que tu fais ces actions

- Tests unitaires + CI GitHub Actions ✅ déjà en place
- Une fois ton `paybyphone_flow.json` reçu : je code le vrai client `boring.payment.paybyphone` (remplace le stub `dry_run`)
- Une fois ton `models/best.pt` produit : je peux affiner la pipeline glue (cooldown adaptatif, multi-provider, etc.)
- Doc + landing page : sur demande

---

## Récap des fichiers que je vais te demander

| Quand | Fichier | Comment me l'envoyer |
|-------|---------|----------------------|
| Après Action #2 | `datasets/control_vehicle_v1.zip` (export Roboflow brut) | Drag-drop dans le chat OU lien Drive/WeTransfer |
| Après Action #3 | `models/best.pt` | Drag-drop OU push direct sur le repo dans un commit séparé |
| Après Action #4 | `scripts/paybyphone_endpoints.json` (credentials déjà masqués) | Drag-drop dans le chat |
