"""Geofence Lille — point-in-polygon contre les zones payantes data.gouv.fr."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from shapely.geometry import Point, shape
from shapely.prepared import prep

console = Console()

DEFAULT_ZONES_PATH = Path("data/lille_parking_zones.geojson")


class LilleParkingZones:
    def __init__(self, geojson_path: Path = DEFAULT_ZONES_PATH) -> None:
        if not geojson_path.exists():
            raise FileNotFoundError(
                f"Zones non trouvées à {geojson_path}. "
                "Lance `make zones` ou `python scripts/download_lille_zones.py`."
            )
        with open(geojson_path) as f:
            data = json.load(f)
        self.polygons = [prep(shape(feat["geometry"])) for feat in data["features"]]
        self.zone_count = len(self.polygons)
        console.print(f"[dim]Geofence Lille chargée : {self.zone_count} zones payantes[/dim]")

    def is_in_paid_zone(self, lat: float, lon: float) -> bool:
        pt = Point(lon, lat)  # GeoJSON : (lon, lat)
        return any(poly.contains(pt) for poly in self.polygons)
