"""Vertical Boring Contest — contestation administrative (FPS, amendes, etc.).

Architecture symétrique à `boring.payment` :
- `base.py`     : interface `ContestProvider` + dataclass `ContestCase`
- `rapo.py`     : client pour le Recours Administratif Préalable Obligatoire (FPS)

Mode dry_run par défaut tant que les intégrations LRAR (AR24, Maileva) ne sont
pas branchées + tant que le générateur LLM de courriers n'est pas validé.

Cf. vault Boring/IDEAS/PAIN-POINTS-FR-v2.md — vertical Boring FPS score 2880.
"""

from boring.contest.base import (
    ContestCase,
    ContestKind,
    ContestProvider,
    ContestStatus,
    SubmissionReceipt,
)
from boring.contest.rapo import RAPOContestClient

__all__ = [
    "ContestCase",
    "ContestKind",
    "ContestProvider",
    "ContestStatus",
    "RAPOContestClient",
    "SubmissionReceipt",
]


CONTEST_REGISTRY: dict[str, type[ContestProvider]] = {
    "rapo": RAPOContestClient,
}


def get_contest_provider(name: str) -> type[ContestProvider]:
    """Retourne la classe de contestation correspondante."""
    key = name.lower().strip()
    if key not in CONTEST_REGISTRY:
        raise KeyError(
            f"Contest provider inconnu : {name!r}. Choix : {', '.join(sorted(CONTEST_REGISTRY))}"
        )
    return CONTEST_REGISTRY[key]
