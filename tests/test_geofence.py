"""Tests du module geofence Lille."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boring.geofence import LilleParkingZones


def test_loads_default_zones():
    z = LilleParkingZones()
    assert z.zone_count >= 1


def test_point_inside_lille_centre():
    z = LilleParkingZones()
    # Place du Théâtre, plein cœur de Lille
    assert z.is_in_paid_zone(50.6371, 3.0633) is True


def test_point_outside_lille():
    z = LilleParkingZones()
    # Champ rural à 30km au sud
    assert z.is_in_paid_zone(50.3000, 2.5000) is False


def test_point_wazemmes():
    z = LilleParkingZones()
    assert z.is_in_paid_zone(50.6280, 3.0500) is True


def test_missing_file_raises(tmp_path: Path):
    fake = tmp_path / "missing.geojson"
    with pytest.raises(FileNotFoundError):
        LilleParkingZones(geojson_path=fake)


def test_custom_geojson_loads(tmp_path: Path):
    """Vérifie qu'un GeoJSON custom est correctement chargé."""
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }
    p = tmp_path / "custom.geojson"
    p.write_text(json.dumps(gj))
    z = LilleParkingZones(geojson_path=p)
    assert z.zone_count == 1
    assert z.is_in_paid_zone(0.5, 0.5) is True
    assert z.is_in_paid_zone(2.0, 2.0) is False
