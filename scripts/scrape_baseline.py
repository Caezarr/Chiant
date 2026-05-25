"""Scraper baseline pour constituer ~100-200 images de véhicules de contrôle.

Utilise DuckDuckGo Images (pas d'API key requise). Dédup par hash perceptuel.
Sortie : datasets/baseline/.

Workflow Gabriel :
    1. uv sync --dev      (installe ddgs + imagehash)
    2. uv run python scripts/scrape_baseline.py
    3. Inspecter datasets/baseline/, supprimer les faux positifs manuellement
    4. Upload sur Roboflow comme dataset de base, annoter
    5. Compléter par captation terrain Lille (HUMAN-TODO Action #1)

Limites :
- Le scraping web est fragile : queries qui marchent aujourd'hui peuvent
  céder demain. Le but est de produire un baseline jetable, pas une source
  de vérité.
- La qualité est variable : il y aura ~30% de faux positifs (Smart blanches
  random, voitures de police, etc.). C'est OK, on dédup et on filtre manuel.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import Progress

try:
    from ddgs import DDGS
except ImportError:
    print("ddgs non installé. Lance : uv add --dev ddgs imagehash Pillow", file=sys.stderr)
    sys.exit(1)

try:
    import imagehash
    from PIL import Image
except ImportError:
    print("imagehash + Pillow requis. Lance : uv add --dev imagehash Pillow", file=sys.stderr)
    sys.exit(1)


console = Console()
OUTPUT_DIR = Path("datasets/baseline")
TARGET_PER_QUERY = 30
MIN_IMAGE_WIDTH = 400
DEDUP_HASH_SIZE = 8  # phash 8x8 = 64-bit signature

# Requêtes ciblées sur les véhicules de contrôle automatisé du stationnement.
# Mix de FR (cible) et EN (volume) pour maximiser les hits.
QUERIES = [
    "Streeteo voiture LAPI Paris",
    "Indigo scan car stationnement",
    "voiture radar stationnement France",
    "ANPR parking enforcement car",
    "parking scan car Europe",
    "voiture lecture automatique plaque immatriculation",
    "scan car municipality vehicle ANPR",
    "véhicule contrôle stationnement automatisé",
    "Moovia LAPI Paris",
    "EFFIA voiture contrôle stationnement",
]


def download_image(url: str, dest: Path) -> bool:
    """Télécharge une image, retourne True si succès."""
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        r.raise_for_status()
        # Filtre rapide content-type
        ct = r.headers.get("content-type", "")
        if not ct.startswith("image/"):
            return False
        dest.write_bytes(r.content)
        return True
    except (httpx.HTTPError, OSError):
        return False


def normalize_and_check(path: Path) -> tuple[Path, str] | None:
    """Vérifie taille minimum + recompresse en JPG normalisé. Retourne (new_path, phash) ou None."""
    try:
        img = Image.open(path)
        img.load()
    except (OSError, Image.UnidentifiedImageError):
        path.unlink(missing_ok=True)
        return None

    if min(img.size) < MIN_IMAGE_WIDTH:
        path.unlink(missing_ok=True)
        return None

    # Convert to RGB JPG (uniform)
    if img.mode != "RGB":
        img = img.convert("RGB")
    new_path = path.with_suffix(".jpg")
    img.save(new_path, "JPEG", quality=85)
    if new_path != path:
        path.unlink(missing_ok=True)

    phash = str(imagehash.phash(img, hash_size=DEDUP_HASH_SIZE))
    return new_path, phash


def scrape_query(query: str, count: int, seen_hashes: set[str]) -> int:
    """Scrape une query, ajoute les nouveaux phashes au set, retourne nb d'images ajoutées."""
    added = 0
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=count * 2, safesearch="off"))
    except Exception as e:
        console.print(f"[red]  ✗ DDGS échec sur {query!r} : {e}[/red]")
        return 0

    for i, r in enumerate(results):
        if added >= count:
            break
        url = r.get("image") or r.get("thumbnail")
        if not url:
            continue
        digest = hashlib.md5(url.encode()).hexdigest()[:10]
        tmp = OUTPUT_DIR / f"{digest}.tmp"
        if not download_image(url, tmp):
            continue

        out = normalize_and_check(tmp)
        if out is None:
            continue
        new_path, phash = out

        # Dédup perceptuelle : si on a déjà vu un phash très proche, on ignore
        if phash in seen_hashes:
            new_path.unlink(missing_ok=True)
            continue
        seen_hashes.add(phash)
        added += 1

        # Léger throttle pour éviter d'être blacklisté par DDG
        time.sleep(0.3)

    return added


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seen_hashes: set[str] = set()

    # Charge les phashes déjà existants pour reprendre où on en était
    for existing in OUTPUT_DIR.glob("*.jpg"):
        try:
            seen_hashes.add(str(imagehash.phash(Image.open(existing), hash_size=DEDUP_HASH_SIZE)))
        except Exception:
            pass

    console.print(
        f"[bold]Scraping baseline scan_car[/bold] · "
        f"{len(QUERIES)} queries × ~{TARGET_PER_QUERY} cible · "
        f"reprise depuis {len(seen_hashes)} images existantes"
    )

    total_added = 0
    with Progress(transient=False) as progress:
        task = progress.add_task("queries", total=len(QUERIES))
        for query in QUERIES:
            progress.console.print(f"  → {query!r}")
            added = scrape_query(query, TARGET_PER_QUERY, seen_hashes)
            progress.console.print(f"    [green]+{added}[/green] uniques")
            total_added += added
            progress.update(task, advance=1)

    final_count = len(list(OUTPUT_DIR.glob("*.jpg")))
    console.print(
        f"\n[bold green]Terminé.[/bold green] {total_added} nouvelles, {final_count} total dans {OUTPUT_DIR}\n"
        "[dim]Inspecte les images, supprime les faux positifs manuellement, "
        "puis upload sur Roboflow pour annotation.[/dim]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
