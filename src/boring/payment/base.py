"""Interface abstraite pour les providers de paiement de stationnement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ParkingSession:
    provider: str
    session_id: str
    vehicle_plate: str
    location_id: str
    start: datetime
    end: datetime
    amount_cents: int


class PaymentProvider(ABC):
    name: str

    @abstractmethod
    def login(self, username: str, password: str) -> None: ...

    @abstractmethod
    def get_zone_id(self, lat: float, lon: float) -> str:
        """Retourne le location_id provider à partir de coordonnées GPS."""

    @abstractmethod
    def start_session(
        self,
        vehicle_plate: str,
        location_id: str,
        duration_minutes: int,
    ) -> ParkingSession:
        """Démarre une session de stationnement. Lève sur échec."""

    @abstractmethod
    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None: ...
