"""Scraper baseline pour constituer un dataset initial de vehicules de controle.

Utilise DuckDuckGo Images (pas d'API key requise). Dédup par hash perceptuel.
Sortie : datasets/baseline/{positives,negatives}/ + manifest.jsonl.

Workflow Gabriel :
    1. uv sync --dev      (installe ddgs + imagehash)
    2. uv run python scripts/scrape_baseline.py --profile positives
    3. uv run python scripts/scrape_baseline.py --profile negatives
    4. Inspecter datasets/baseline/, supprimer les faux positifs manuellement
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

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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

POSITIVE_QUERIES = [
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

NEGATIVE_QUERIES = [
    "white utility van street Europe",
    "city car roof camera street view",
    "police car France street",
    "ambulance vehicle France street",
    "taxi roof sign car France",
    "municipal service vehicle France",
    "delivery van parked street",
    "normal car parked street France",
    "parking meter street car France",
    "dashcam city traffic Europe",
]


@dataclass(frozen=True)
class ImageRecord:
    path: str
    url: str
    query: str
    profile: str
    label_hint: str
    phash: str
    width: int
    height: int
    source: str = "duckduckgo-images"
    license_hint: str = "unknown-review-before-training"
    license_status: str = "unknown"
    license_reviewed: bool = False
    created_at: str = ""


def query_profile(profile: str) -> tuple[str, list[str]]:
    if profile == "positives":
        return "control_vehicle_candidate", POSITIVE_QUERIES
    if profile == "negatives":
        return "hard_negative", NEGATIVE_QUERIES
    raise ValueError(f"profile inconnu: {profile}")


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


def normalize_and_check(path: Path) -> tuple[Path, str, tuple[int, int]] | None:
    """Vérifie taille minimum + recompresse en JPG normalisé."""
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

    phash = compute_phash(img)
    return new_path, phash, img.size


def compute_phash(img: Image.Image) -> str:
    return str(imagehash.phash(img, hash_size=DEDUP_HASH_SIZE))


def append_manifest(manifest_path: Path, record: ImageRecord) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(record)
    if not payload["created_at"]:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
    with manifest_path.open("a") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_seen_hashes(root: Path) -> set[str]:
    seen_hashes: set[str] = set()
    for existing in root.glob("**/*.jpg"):
        try:
            seen_hashes.add(compute_phash(Image.open(existing)))
        except Exception:
            pass
    return seen_hashes


def scrape_query(
    query: str,
    count: int,
    seen_hashes: set[str],
    output_dir: Path,
    manifest_path: Path,
    profile: str,
    label_hint: str,
) -> int:
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
        tmp = output_dir / f"{digest}.tmp"
        if not download_image(url, tmp):
            continue

        out = normalize_and_check(tmp)
        if out is None:
            continue
        new_path, phash, size = out

        # Dédup perceptuelle : si on a déjà vu un phash très proche, on ignore
        if phash in seen_hashes:
            new_path.unlink(missing_ok=True)
            continue
        seen_hashes.add(phash)
        append_manifest(
            manifest_path,
            ImageRecord(
                path=str(new_path),
                url=url,
                query=query,
                profile=profile,
                label_hint=label_hint,
                phash=phash,
                width=size[0],
                height=size[1],
            ),
        )
        added += 1

        # Léger throttle pour éviter d'être blacklisté par DDG
        time.sleep(0.3)

    return added


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=("positives", "negatives"),
        default="positives",
        help="Type d'images à collecter.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--count", type=int, default=TARGET_PER_QUERY)
    args = parser.parse_args()

    label_hint, queries = query_profile(args.profile)
    output_dir = args.output / args.profile
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / "manifest.jsonl"

    seen_hashes = load_seen_hashes(args.output)

    console.print(
        f"[bold]Scraping baseline scan_car[/bold] · "
        f"profile={args.profile} · {len(queries)} queries × ~{args.count} cible · "
        f"reprise depuis {len(seen_hashes)} images existantes"
    )

    total_added = 0
    with Progress(transient=False) as progress:
        task = progress.add_task("queries", total=len(queries))
        for query in queries:
            progress.console.print(f"  → {query!r}")
            added = scrape_query(
                query=query,
                count=args.count,
                seen_hashes=seen_hashes,
                output_dir=output_dir,
                manifest_path=manifest_path,
                profile=args.profile,
                label_hint=label_hint,
            )
            progress.console.print(f"    [green]+{added}[/green] uniques")
            total_added += added
            progress.update(task, advance=1)

    final_count = len(list(output_dir.glob("*.jpg")))
    console.print(
        f"\n[bold green]Terminé.[/bold green] {total_added} nouvelles, "
        f"{final_count} total dans {output_dir}\n"
        f"[dim]Manifest : {manifest_path}[/dim]\n"
        "[dim]Inspecte les images, supprime les faux positifs manuellement, "
        "puis upload sur Roboflow pour annotation.[/dim]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
