"""Client Flowbird / Whoosh — STUB.

Note : Flowbird a fusionné avec EasyPark fin 2024. À terme, l'API pourrait
basculer sur EasyPark — vérifier au moment du reverse. Package Android
historique : `group.flowbird.mpp`.

Reverse via HAR : https://flowbird.fr ou app mobile.
"""

from __future__ import annotations

import os

from boring.payment.stub import DryRunParkingProvider

DEFAULT_BASE_URL = os.getenv("FLOWBIRD_API_BASE", "https://api.flowbird.com")


class FlowbirdAPIError(RuntimeError):
    pass


class FlowbirdClient(DryRunParkingProvider):
    name = "flowbird"
    display_name = "Flowbird"
    stub_zone_id = "FLOWBIRD-STUB-ZONE"
    stub_session_prefix = "FB-STUB-"
    stub_amount_cents = 35
    reverse_login_error = "Flowbird reverse à faire : HAR depuis flowbird.fr"
    reverse_zone_error = "Flowbird reverse à faire : mapper les zones depuis le HAR"

    def __init__(self, dry_run: bool = True, base_url: str = DEFAULT_BASE_URL) -> None:
        super().__init__(dry_run=dry_run, base_url=base_url)
