"""Télécharge les zones de stationnement payant à Lille.

⚠️ État au 25 mai 2026 : le portail OpenData MEL a migré
(opendata.lillemetropole.fr → data.lillemetropole.fr / geOrchestra)
et la nouvelle API publique n'est pas encore mappée. Ce script tente
plusieurs URLs candidates ; en cas d'échec total, le fallback hardcodé
(bounding box du centre-ville, commité dans le repo) est conservé.

À ré-investiguer périodiquement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from rich.console import Console

console = Console()

# URLs candidates, par ordre de préférence
CANDIDATE_URLS = [
    # Ancien Opendatasoft (HS depuis migration)
    "https://opendata.lillemetropole.fr/api/explore/v2.1/catalog/datasets/zone-stationnement-payant/exports/geojson",
    # data.gouv.fr (proxy potentiel)
    "https://www.data.gouv.fr/fr/datasets/r/zone-stationnement-payant.geojson",
]

OUTPUT = Path("data/lille_parking_zones.geojson")


def looks_like_geojson(content: bytes) -> bool:
    head = content[:200].lstrip()
    return head.startswith(b"{") and (b'"FeatureCollection"' in content[:2000] or b'"Feature"' in content[:2000])


def try_download(url: str) -> bytes | None:
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        console.print(f"[dim]  ✗ {url[:70]}… : {e}[/dim]")
        return None
    if not looks_like_geojson(r.content):
        console.print(f"[dim]  ✗ {url[:70]}… : pas du GeoJSON (HTML probable)[/dim]")
        return None
    return r.content


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    console.print("[bold]Recherche des zones de stationnement payant Lille[/bold]")
    for url in CANDIDATE_URLS:
        console.print(f"[dim]→ {url[:90]}…[/dim]")
        content = try_download(url)
        if content:
            OUTPUT.write_bytes(content)
            size_kb = len(content) / 1024
            console.print(f"[green]✓[/green] {OUTPUT} ({size_kb:.1f} KB) depuis source vivante")
            return 0
    console.print(
        "[yellow]⚠ Aucune source live trouvée.[/yellow] "
        f"Conservation du fallback existant : {OUTPUT}"
    )
    if not OUTPUT.exists():
        console.print(f"[red]✗ Pas de fallback non plus à {OUTPUT}. Vérifie le repo.[/red]")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
