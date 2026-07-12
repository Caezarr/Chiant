"""Catalogue des sources gratuites pour construire le dataset vision."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TRAINABLE_POLICIES = {
    "allowed-with-license-review",
    "candidate-review-required",
    "allowed-if-dataset-license-allows",
}


@dataclass(frozen=True)
class VisionSource:
    id: str
    name: str
    url: str
    usage: tuple[str, ...]
    free: bool
    license_status: str
    train_policy: str
    action: str

    @property
    def trainable_candidate(self) -> bool:
        return self.free and self.train_policy in TRAINABLE_POLICIES


@dataclass(frozen=True)
class VisionSourceCatalog:
    version: int
    updated_at: str
    sources: list[VisionSource]

    def count_trainable(self, usage: str) -> int:
        return sum(
            1 for source in self.sources if usage in source.usage and source.trainable_candidate
        )


def load_source_catalog(path: Path) -> VisionSourceCatalog:
    payload = json.loads(path.read_text())
    sources = [
        VisionSource(
            id=str(item["id"]),
            name=str(item["name"]),
            url=str(item["url"]),
            usage=tuple(str(value) for value in item.get("usage", [])),
            free=bool(item.get("free")),
            license_status=str(item["license_status"]),
            train_policy=str(item["train_policy"]),
            action=str(item["action"]),
        )
        for item in payload.get("sources", [])
    ]
    return VisionSourceCatalog(
        version=int(payload.get("version", 0)),
        updated_at=str(payload.get("updated_at", "")),
        sources=sources,
    )
