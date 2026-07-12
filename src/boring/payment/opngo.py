"""Client OPnGO / Indigo Neo — STUB.

Groupe Indigo. Renommée Indigo Neo en 2023.

OPnGO a historiquement exposé une API publique : https://developer.opngo.com/
(à vérifier post-rebrand). Si toujours actif, c'est la seule API parking FR
avec un tier gratuit utilisable directement sans accord commercial — à privilégier
en priorité pour Boring.
"""

from __future__ import annotations

import os

from boring.payment.stub import DryRunParkingProvider, console

DEFAULT_BASE_URL = os.getenv("OPNGO_API_BASE", "https://api.opngo.com")


class OPnGOAPIError(RuntimeError):
    pass


class OPnGOClient(DryRunParkingProvider):
    name = "opngo"
    display_name = "OPnGO"
    stub_zone_id = "OPNGO-STUB-ZONE"
    stub_session_prefix = "OP-STUB-"
    stub_amount_cents = 30
    reverse_login_error = "OPNGO_API_KEY non défini dans .env"
    reverse_zone_error = "À implémenter une fois doc OPnGO développeur validée"

    def __init__(self, dry_run: bool = True, base_url: str = DEFAULT_BASE_URL) -> None:
        super().__init__(dry_run=dry_run, base_url=base_url)
        self._api_key = os.getenv("OPNGO_API_KEY")

    def login(self, username: str, password: str) -> None:
        # OPnGO utilise probablement un API key plutôt que user/pass — set via env
        if self.dry_run:
            console.print("[yellow][DRY-RUN] OPnGO via API key[/yellow]")
            return
        if not self._api_key:
            raise OPnGOAPIError("OPNGO_API_KEY non défini dans .env")
