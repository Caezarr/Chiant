from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.scrape_baseline import (
    ImageRecord,
    append_manifest,
    load_seen_hashes,
    query_profile,
)


def test_query_profile_known_profiles():
    positive_label, positive_queries = query_profile("positives")
    negative_label, negative_queries = query_profile("negatives")

    assert positive_label == "control_vehicle_candidate"
    assert negative_label == "hard_negative"
    assert positive_queries
    assert negative_queries


def test_query_profile_rejects_unknown():
    with pytest.raises(ValueError):
        query_profile("other")


def test_append_manifest_jsonl(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    append_manifest(
        manifest,
        ImageRecord(
            path="datasets/baseline/positives/a.jpg",
            url="https://example.com/a.jpg",
            query="voiture LAPI",
            profile="positives",
            label_hint="control_vehicle_candidate",
            phash="abc",
            width=640,
            height=480,
        ),
    )

    payload = json.loads(manifest.read_text().strip())
    assert payload["path"] == "datasets/baseline/positives/a.jpg"
    assert payload["license_hint"] == "unknown-review-before-training"
    assert payload["license_status"] == "unknown"
    assert payload["license_reviewed"] is False
    assert payload["created_at"]


def test_load_seen_hashes_empty_dir(tmp_path: Path):
    assert load_seen_hashes(tmp_path) == set()
