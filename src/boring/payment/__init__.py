"""Clients de paiement de stationnement.

Architecture : tous les providers implémentent `PaymentProvider` (cf. `base.py`),
ce qui permet à la glue d'en sélectionner un via la variable d'env
`PAYMENT_PROVIDER` sans changer le reste du code.

Providers actuels :
- `paybyphone`        — client API réel (squelette, mode dry_run par défaut)
- `paybyphone-assisted` — rappel iMessage légalement défendable
- `easypark`          — stub (reverse à faire)
- `flowbird`          — stub (reverse à faire, fusion EasyPark en cours)
- `opngo`             — stub (API officielle existe, à valider)
"""

from boring.payment.assisted import AssistedPayByPhone
from boring.payment.base import ParkingSession, PaymentProvider
from boring.payment.easypark import EasyParkClient
from boring.payment.flowbird import FlowbirdClient
from boring.payment.opngo import OPnGOClient
from boring.payment.paybyphone import PayByPhoneClient

__all__ = [
    "AssistedPayByPhone",
    "EasyParkClient",
    "FlowbirdClient",
    "OPnGOClient",
    "ParkingSession",
    "PayByPhoneClient",
    "PaymentProvider",
]


PROVIDER_REGISTRY: dict[str, type[PaymentProvider]] = {
    "paybyphone": PayByPhoneClient,
    "paybyphone-assisted": AssistedPayByPhone,
    "easypark": EasyParkClient,
    "flowbird": FlowbirdClient,
    "opngo": OPnGOClient,
}


def get_provider_class(name: str) -> type[PaymentProvider]:
    """Retourne la classe provider correspondante. Lève KeyError si inconnu."""
    key = name.lower().strip()
    if key not in PROVIDER_REGISTRY:
        raise KeyError(
            f"Provider inconnu : {name!r}. Choix possibles : {', '.join(sorted(PROVIDER_REGISTRY))}"
        )
    return PROVIDER_REGISTRY[key]
