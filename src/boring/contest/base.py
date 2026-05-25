"""Interface abstraite pour les providers de contestation administrative."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class ContestKind(str, Enum):
    """Type de contestation supporté."""

    FPS_RAPO = "fps_rapo"  # Recours administratif préalable obligatoire FPS
    FPS_CCSP = "fps_ccsp"  # Saisine Commission du contentieux du stationnement payant
    RADAR = "radar"  # Contestation radar / amende routière
    CAF = "caf"  # Recours CAF (futur)
    FRANCE_TRAVAIL = "france_travail"  # Recours France Travail (futur)


class ContestStatus(str, Enum):
    DRAFTED = "drafted"  # Dossier monté, courrier généré
    SUBMITTED = "submitted"  # LRAR envoyée
    ACKNOWLEDGED = "acknowledged"  # AR reçu
    ACCEPTED = "accepted"  # Contestation acceptée
    REJECTED = "rejected"  # Refus
    ESCALATED = "escalated"  # Escaladé (CCSP, médiateur, tribunal)


@dataclass
class ContestCase:
    """Un dossier de contestation en cours.

    Le cycle de vie : DRAFTED → SUBMITTED → ACKNOWLEDGED → ACCEPTED|REJECTED.
    Si REJECTED, peut être ESCALATED vers une instance supérieure.
    """

    case_id: str
    kind: ContestKind
    user_id: str  # Référence vers l'user Boring (anonymisé)
    subject: str  # Ex: "FPS n° 2026-LL-12345"
    reason: str  # Motif principal de contestation (user input)
    evidence_paths: list[Path] = field(default_factory=list)  # photos, justificatifs
    drafted_letter: str | None = None  # courrier généré (markdown ou texte)
    recipient_address: str | None = None  # adresse de la collectivité ou opérateur
    amount_eur: float = 0.0  # montant en jeu (€)
    status: ContestStatus = ContestStatus.DRAFTED
    created_at: datetime = field(default_factory=datetime.now)
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None


@dataclass
class SubmissionReceipt:
    """Accusé d'envoi d'une LRAR digitale."""

    case_id: str
    provider: str  # "ar24" | "maileva" | "dry_run"
    tracking_id: str
    sent_at: datetime
    cost_cents: int  # coût de l'envoi


class ContestProvider(ABC):
    """Interface commune à tous les types de contestation."""

    name: str
    kind: ContestKind

    @abstractmethod
    def prepare_case(
        self,
        user_id: str,
        subject: str,
        reason: str,
        evidence_paths: list[Path] | None = None,
        amount_eur: float = 0.0,
    ) -> ContestCase:
        """Monte le dossier et génère le courrier de contestation.

        Le courrier doit être placé dans `case.drafted_letter`. Le statut
        retourné est `DRAFTED`. Le user (ou le code Boring) appelle ensuite
        `submit()` pour envoyer la LRAR.
        """

    @abstractmethod
    def submit(self, case: ContestCase) -> SubmissionReceipt:
        """Envoie la LRAR digitale et passe le statut à SUBMITTED."""

    @abstractmethod
    def get_status(self, case_id: str) -> ContestStatus:
        """Retourne le statut courant du dossier."""

    @abstractmethod
    def escalate(self, case: ContestCase) -> ContestCase:
        """Escalade un cas REJECTED vers l'instance suivante (ex: RAPO → CCSP)."""
