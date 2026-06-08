"""Client de contestation FPS via RAPO — Recours Administratif Préalable Obligatoire.

État pre-alpha : générateur de courrier en mode template + LLM stub.
À brancher :
- Un vrai LLM (Claude/GPT-4) pour personnaliser le courrier au cas
- Un client LRAR digitale (AR24 ou Maileva) pour l'envoi
- Une base de jurisprudence RAPO/CCSP par commune

Workflow utilisateur cible :
    1. User photographie son FPS + uploade preuves (photo zone, horodateur, etc.)
    2. User décrit le motif en 1-2 phrases
    3. boring.contest génère le courrier RAPO en <60s
    4. Boring envoie en LRAR digitale, suit le délai 1 mois
    5. Si refus → escalade CCSP automatique
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from rich.console import Console

from boring.contest.base import (
    ContestCase,
    ContestKind,
    ContestProvider,
    ContestStatus,
    SubmissionReceipt,
)

console = Console()


RAPO_LETTER_TEMPLATE = """\
{recipient_name}
{recipient_address}

À {city}, le {today}

Objet : RECOURS ADMINISTRATIF PRÉALABLE OBLIGATOIRE (RAPO)
contre le forfait post-stationnement n° {subject}
Montant contesté : {amount} €

Madame, Monsieur,

Conformément à l'article L.2333-87 du Code général des collectivités territoriales et à l'article R.2333-120-1 du même code, je conteste par la présente le forfait post-stationnement référencé ci-dessus, qui m'a été notifié le {notification_date_placeholder}.

Motif de la contestation :
{reason}

Pièces justificatives jointes :
{evidence_list}

En conséquence, je vous demande de bien vouloir annuler ce forfait post-stationnement et m'en notifier la décision par courrier recommandé dans le délai d'un mois prévu par les textes.

À défaut de réponse favorable de votre part dans ce délai, je me réserve le droit de saisir la Commission du contentieux du stationnement payant (CCSP) conformément à l'article L.2333-87-1 du CGCT.

Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.

{user_signature_placeholder}
"""


class RAPOContestClient(ContestProvider):
    """Client de contestation FPS via RAPO. Mode dry_run par défaut."""

    name = "rapo"
    kind = ContestKind.FPS_RAPO

    def __init__(self, dry_run: bool = True, use_ai: bool = True) -> None:
        self.dry_run = dry_run
        self.use_ai = use_ai
        self._cases: dict[str, ContestCase] = {}

    def prepare_case(
        self,
        user_id: str,
        subject: str,
        reason: str,
        evidence_paths: list[Path] | None = None,
        amount_eur: float = 35.0,
    ) -> ContestCase:
        case_id = f"RAPO-{uuid.uuid4().hex[:10]}"
        evidence = evidence_paths or []
        evidence_list = (
            "\n".join(f"  - {p.name}" for p in evidence)
            if evidence
            else "  - (aucune pièce jointe)"
        )

        if self.use_ai and not self.dry_run:
            letter = self._generate_with_claude(subject, reason, amount_eur)
        else:
            letter = RAPO_LETTER_TEMPLATE.format(
                recipient_name="Direction du stationnement",
                recipient_address="[À renseigner — adresse de la collectivité]",
                city="[Ville]",
                today=datetime.now().strftime("%d %B %Y"),
                subject=subject,
                amount=f"{amount_eur:.2f}",
                notification_date_placeholder="[date de notification]",
                reason=reason.strip(),
                evidence_list=evidence_list,
                user_signature_placeholder="[Nom Prénom + signature]",
            )

        case = ContestCase(
            case_id=case_id,
            kind=self.kind,
            user_id=user_id,
            subject=subject,
            reason=reason,
            evidence_paths=evidence,
            drafted_letter=letter,
            amount_eur=amount_eur,
            status=ContestStatus.DRAFTED,
        )
        self._cases[case_id] = case
        console.print(
            f"[green]✓[/green] RAPO drafted : {case_id} · "
            f"{len(letter.splitlines())} lignes · {amount_eur:.2f}€ contestés"
        )
        return case

    def _generate_with_claude(self, subject: str, reason: str, amount_eur: float) -> str:
        client = anthropic.Anthropic()
        today = datetime.now().strftime("%d %B %Y")
        prompt = f"""Tu es un expert juridique spécialisé en droit du stationnement français.
Génère un courrier RAPO (Recours Administratif Préalable Obligatoire) complet, formel et percutant.

Référence FPS : {subject}
Montant contesté : {amount_eur:.2f}€
Motif fourni par l'usager : {reason}
Date du jour : {today}

Le courrier doit :
- Citer les articles L.2333-87 et R.2333-120-1 du CGCT
- Mentionner le droit de saisir la CCSP en cas de refus dans 1 mois
- Être adressé à "Monsieur/Madame le Directeur du stationnement"
- Laisser des placeholders [NOM PRÉNOM], [ADRESSE], [DATE DE NOTIFICATION], [SIGNATURE] pour que l'utilisateur complète
- Être en français formel, ~400 mots
- Être persuasif et bien structuré

Retourne uniquement le texte du courrier, sans explication."""
        message = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def submit(self, case: ContestCase) -> SubmissionReceipt:
        if case.status != ContestStatus.DRAFTED:
            raise RuntimeError(f"Cas {case.case_id} non DRAFTED (status: {case.status})")
        if self.dry_run:
            console.print(f"[yellow][DRY-RUN][/yellow] envoi LRAR pour {case.case_id}")
            receipt = SubmissionReceipt(
                case_id=case.case_id,
                provider="dry_run",
                tracking_id=f"DRYTRACK-{uuid.uuid4().hex[:8]}",
                sent_at=datetime.now(),
                cost_cents=0,
            )
        else:
            raise NotImplementedError(
                "Envoi LRAR réel à implémenter : AR24 ou Maileva. "
                "Cf. https://www.ar24.fr ou https://www.docaposte.com/maileva."
            )

        case.status = ContestStatus.SUBMITTED
        case.submitted_at = receipt.sent_at
        return receipt

    def get_status(self, case_id: str) -> ContestStatus:
        if case_id not in self._cases:
            raise KeyError(f"Cas inconnu : {case_id}")
        return self._cases[case_id].status

    def escalate(self, case: ContestCase) -> ContestCase:
        if case.status != ContestStatus.REJECTED:
            raise RuntimeError(
                f"Seuls les cas REJECTED peuvent être escaladés (status actuel: {case.status})"
            )
        # On clone le cas en CCSP. À l'avenir : générer une saisine CCSP via
        # https://tribunal-stationnement-payant.fr
        escalated_id = f"CCSP-{uuid.uuid4().hex[:10]}"
        escalated = ContestCase(
            case_id=escalated_id,
            kind=ContestKind.FPS_CCSP,
            user_id=case.user_id,
            subject=f"Suite à RAPO refusé : {case.subject}",
            reason=case.reason,
            evidence_paths=case.evidence_paths,
            amount_eur=case.amount_eur,
            status=ContestStatus.DRAFTED,
        )
        case.status = ContestStatus.ESCALATED
        self._cases[escalated_id] = escalated
        console.print(f"[cyan]↗[/cyan] Escaladé vers CCSP : {case.case_id} → {escalated_id}")
        return escalated
