"""Client EasyPark — STUB.

Doc officielle B2B : https://developer.easyparkgroup.com/
Partner API existante mais accès commercial requis. Endpoints réels à mapper
via HAR (`https://m.easypark.fr` ou `https://easypark.fr`) puis
`scripts/parse_provider_har.py easypark`.

Note : Flowbird/Whoosh a fusionné avec EasyPark fin 2024, les APIs migrent
progressivement. Vérifier au moment du reverse si EasyPark sert aussi les
zones historiquement Flowbird.
"""

from __future__ import annotations

import os

from boring.payment.stub import DryRunParkingProvider

DEFAULT_BASE_URL = os.getenv("EASYPARK_API_BASE", "https://api.easypark.com")


class EasyParkClient(DryRunParkingProvider):
    name = "easypark"
    display_name = "EasyPark"
    stub_zone_id = "EASYPARK-STUB-ZONE"
    stub_session_prefix = "EP-STUB-"
    stub_amount_cents = 35
    reverse_login_error = "EasyPark reverse à faire : HAR depuis m.easypark.fr"
    reverse_zone_error = "EasyPark reverse à faire : mapper les zones depuis le HAR"

    def __init__(self, dry_run: bool = True, base_url: str = DEFAULT_BASE_URL) -> None:
        super().__init__(dry_run=dry_run, base_url=base_url)
