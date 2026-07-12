from __future__ import annotations

import json
from pathlib import Path

from boring.vision_sources import load_source_catalog


def test_load_source_catalog_counts_trainable_sources(tmp_path: Path):
    catalog_path = tmp_path / "sources.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-07-11",
                "sources": [
                    _source("open-images", ["negatives"], "allowed-with-license-review"),
                    _source("mapillary", ["positives", "negatives"], "candidate-review-required"),
                    _source("video", ["positives"], "validation-only-do-not-train"),
                ],
            }
        )
    )

    catalog = load_source_catalog(catalog_path)

    assert catalog.count_trainable("positives") == 1
    assert catalog.count_trainable("negatives") == 2
    assert catalog.sources[2].trainable_candidate is False


def _source(source_id: str, usage: list[str], policy: str) -> dict:
    return {
        "id": source_id,
        "name": source_id,
        "url": "https://example.test",
        "usage": usage,
        "free": True,
        "license_status": "review-required",
        "train_policy": policy,
        "action": "review",
    }
