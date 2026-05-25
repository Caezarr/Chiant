"""Tests du module boring.contest."""

from __future__ import annotations

from pathlib import Path

import pytest

from boring.contest import (
    CONTEST_REGISTRY,
    ContestCase,
    ContestKind,
    ContestStatus,
    RAPOContestClient,
    SubmissionReceipt,
    get_contest_provider,
)
from boring.contest.base import ContestProvider


def test_registry_contains_rapo():
    assert "rapo" in CONTEST_REGISTRY
    assert get_contest_provider("rapo") is RAPOContestClient


def test_get_contest_provider_unknown_raises():
    with pytest.raises(KeyError):
        get_contest_provider("ghost-contest")


def test_rapo_implements_provider_interface():
    p = RAPOContestClient(dry_run=True)
    assert isinstance(p, ContestProvider)
    assert p.name == "rapo"
    assert p.kind == ContestKind.FPS_RAPO


def test_rapo_prepare_case_generates_letter():
    p = RAPOContestClient(dry_run=True)
    case = p.prepare_case(
        user_id="user-001",
        subject="FPS-2026-LL-12345",
        reason="J'avais payé via PayByPhone à 14h32, le scan a eu lieu à 14h35.",
        amount_eur=35.0,
    )
    assert isinstance(case, ContestCase)
    assert case.status == ContestStatus.DRAFTED
    assert case.case_id.startswith("RAPO-")
    assert case.drafted_letter is not None
    assert "RECOURS ADMINISTRATIF PRÉALABLE OBLIGATOIRE" in case.drafted_letter
    assert "FPS-2026-LL-12345" in case.drafted_letter
    assert "PayByPhone" in case.drafted_letter  # le motif est inclus


def test_rapo_prepare_case_with_evidence():
    p = RAPOContestClient(dry_run=True)
    evidence = [Path("photo1.jpg"), Path("receipt.pdf")]
    case = p.prepare_case(
        user_id="user-001",
        subject="FPS-XYZ",
        reason="Test",
        evidence_paths=evidence,
        amount_eur=50.0,
    )
    assert case.evidence_paths == evidence
    assert "photo1.jpg" in case.drafted_letter
    assert "receipt.pdf" in case.drafted_letter


def test_rapo_submit_dry_run():
    p = RAPOContestClient(dry_run=True)
    case = p.prepare_case(user_id="u", subject="s", reason="r", amount_eur=10.0)
    receipt = p.submit(case)
    assert isinstance(receipt, SubmissionReceipt)
    assert receipt.provider == "dry_run"
    assert case.status == ContestStatus.SUBMITTED
    assert case.submitted_at is not None


def test_rapo_submit_rejects_non_drafted():
    p = RAPOContestClient(dry_run=True)
    case = p.prepare_case(user_id="u", subject="s", reason="r", amount_eur=10.0)
    p.submit(case)
    # Submit twice → erreur car déjà SUBMITTED
    with pytest.raises(RuntimeError):
        p.submit(case)


def test_rapo_escalate_rejected_to_ccsp():
    p = RAPOContestClient(dry_run=True)
    case = p.prepare_case(user_id="u", subject="FPS-1", reason="r", amount_eur=35.0)
    case.status = ContestStatus.REJECTED  # simulate refus
    escalated = p.escalate(case)
    assert escalated.kind == ContestKind.FPS_CCSP
    assert escalated.case_id.startswith("CCSP-")
    assert escalated.status == ContestStatus.DRAFTED
    assert case.status == ContestStatus.ESCALATED


def test_rapo_escalate_rejects_non_rejected():
    p = RAPOContestClient(dry_run=True)
    case = p.prepare_case(user_id="u", subject="s", reason="r", amount_eur=10.0)
    # DRAFTED, pas REJECTED → escalate doit refuser
    with pytest.raises(RuntimeError):
        p.escalate(case)
