# HUMAN-TODO — Ce que toi (Gabriel) tu dois faire

> Tout le reste est ou sera automatisé côté code.
> Chaque étape débloque la suivante. Si tu en sautes une, je peux pas avancer.

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

## ⏳ Action #4 — Capture intégration paiement (1h)

**Durée** : 1h
**Sortie attendue** : `scripts/paybyphone_flow.json` (à m'envoyer)

### Comment

1. Sur ton Mac :
   ```bash
   cd /Users/gabriel/Desktop/GR/boring
   uv run mitmproxy -s scripts/paybyphone_capture.py
   ```
   (mitmproxy écoute sur `127.0.0.1:8080`)

2. Trouve ton IP locale :
   ```bash
   ipconfig getifaddr en0   # ou en1 si Wi-Fi vs Ethernet
   ```

3. Sur ton iPhone :
   - **Réglages > Wi-Fi** > (i) à côté de ton réseau > **Configurer le proxy** → Manuel
   - **Serveur** : ton IP Mac (étape 2)
   - **Port** : `8080`
   - Sauvegarder

4. Toujours sur iPhone, Safari → ouvre **http://mitm.it** → télécharge le profil iOS → installe :
   - Réglages > Général > VPN et gestion d'appareils > installe le profil
   - Réglages > Général > Informations > **Certificats de confiance** > active "mitmproxy"

5. Ouvre l'app PayByPhone sur iPhone :
   - **Login** avec ton compte
   - Renseigne ta plaque
   - **Démarre une session de stationnement** 15 minutes (à un endroit réel de Lille)
   - Vérifie qu'elle apparaît bien comme active
   - **Stoppe la session** (pour pas payer pour rien, et capturer aussi le flow d'arrêt)

6. Sur Mac, dans mitmproxy : tape `q` puis `y` pour quitter.

7. Le fichier `scripts/paybyphone_flow.json` est créé. **Envoie-le moi.**

8. Remets le proxy iPhone sur "Désactivé" pour pas tout faire passer par mitmproxy en permanence.

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
| Après Action #4 | `scripts/paybyphone_flow.json` | Drag-drop dans le chat (penser à anonymiser plaque si visible) |
