"""Client PayByPhone — implémentation basée sur la doc communautaire.

Référence : https://github.com/itsff/PayByPhone-api-docs
Endpoints attendus (à confirmer via HAR capture côté Gabriel) :
    POST /auth/token                              → OAuth2 password grant
    GET  /parking/accounts                        → liste des comptes
    GET  /parking/locations?lat=&lng=             → résolution zone à partir GPS
    POST /parking/accounts/{accountId}/sessions   → démarre une session
    GET  /parking/accounts/{accountId}/sessions/current

Headers communs :
    Authorization: Bearer <token>
    X-Pbp-Version: 2

Le client a deux modes :
- `dry_run=True` (défaut) : ne fait aucun appel réseau, retourne des sessions
  factices. Utilisé tant qu'on n'a pas validé les endpoints réels.
- `dry_run=False` : appels HTTP réels, à activer après validation HAR.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from rich.console import Console

from boring.payment.base import ParkingSession, PaymentProvider

console = Console()

# URLs candidates — à confirmer/écraser par la valeur trouvée dans le HAR
DEFAULT_BASE_URL = os.getenv("PAYBYPHONE_API_BASE", "https://api.paybyphone.com")
DEFAULT_AUTH_URL = os.getenv("PAYBYPHONE_AUTH_URL", f"{DEFAULT_BASE_URL}/auth/token")
DEFAULT_TIMEOUT = 15.0
COMMON_HEADERS = {
    "X-Pbp-Version": "2",
    "Accept": "application/json",
    "User-Agent": "Boring/0.1 (mobile-like)",
}


@dataclass
class _AuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: datetime


class PayByPhoneAuthError(RuntimeError):
    """Échec d'authentification."""


class PayByPhoneAPIError(RuntimeError):
    """Échec d'appel API (4xx/5xx/inattendu)."""


class PayByPhoneClient(PaymentProvider):
    """Client API PayByPhone.

    Note : tant que `dry_run=True`, aucune requête réseau réelle.
    """

    name = "paybyphone"

    def __init__(
        self,
        dry_run: bool = True,
        base_url: str = DEFAULT_BASE_URL,
        auth_url: str = DEFAULT_AUTH_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.dry_run = dry_run
        self.base_url = base_url.rstrip("/")
        self.auth_url = auth_url
        self._token: _AuthToken | None = None
        self._account_id: str | None = None
        self._client = httpx.Client(timeout=timeout, headers=COMMON_HEADERS)

    # ---------- Auth ----------

    def login(self, username: str, password: str) -> None:
        if self.dry_run:
            console.print(f"[yellow][DRY-RUN] login as {username or '<empty>'}[/yellow]")
            self._token = _AuthToken("STUB", None, datetime.max)
            self._account_id = "STUB-ACCOUNT"
            return

        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            # client_id à ajuster après HAR
            "client_id": os.getenv("PAYBYPHONE_CLIENT_ID", "paybyphone-mobile"),
        }
        try:
            r = self._client.post(self.auth_url, data=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            raise PayByPhoneAuthError(f"login failed : {e}") from e

        self._token = _AuthToken(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=datetime.now() + timedelta(seconds=int(data.get("expires_in", 3600))),
        )
        self._authorize_client()
        self._fetch_account_id()

    def _authorize_client(self) -> None:
        if self._token is None:
            return
        self._client.headers["Authorization"] = f"Bearer {self._token.access_token}"

    def _fetch_account_id(self) -> None:
        r = self._client.get(f"{self.base_url}/parking/accounts")
        r.raise_for_status()
        accounts = r.json()
        # Format attendu : list[{"accountId": "...", ...}] — à confirmer via HAR
        if not accounts:
            raise PayByPhoneAPIError("aucun compte PayByPhone trouvé")
        self._account_id = accounts[0].get("accountId") or accounts[0].get("id")

    # ---------- Locations ----------

    def get_zone_id(self, lat: float, lon: float) -> str:
        if self.dry_run:
            return "LILLE-STUB-ZONE"
        r = self._client.get(f"{self.base_url}/parking/locations", params={"lat": lat, "lng": lon})
        r.raise_for_status()
        locations = r.json()
        if not locations:
            raise PayByPhoneAPIError(f"aucune zone trouvée à ({lat},{lon})")
        # On prend la zone la plus proche — adapté après HAR
        return locations[0].get("locationId") or locations[0].get("id")

    # ---------- Sessions ----------

    def start_session(
        self,
        vehicle_plate: str,
        location_id: str,
        duration_minutes: int,
    ) -> ParkingSession:
        if self.dry_run:
            now = datetime.now()
            return ParkingSession(
                provider=self.name,
                session_id=f"STUB-{int(now.timestamp())}",
                vehicle_plate=vehicle_plate,
                location_id=location_id,
                start=now,
                end=now + timedelta(minutes=duration_minutes),
                amount_cents=30,
            )

        if not self._account_id:
            raise PayByPhoneAPIError("non authentifié — appeler login() d'abord")

        start_time = datetime.now()
        payload = {
            "locationId": location_id,
            "licensePlate": vehicle_plate,
            "duration": {"timeUnit": "Minutes", "quantity": duration_minutes},
            "startTime": start_time.isoformat(timespec="seconds"),
            # rateOptionId + paymentMethod à compléter via HAR
        }
        try:
            r = self._client.post(
                f"{self.base_url}/parking/accounts/{self._account_id}/sessions",
                json=payload,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise PayByPhoneAPIError(f"start session échec : {e}") from e

        data = r.json() if r.content else {}
        end_time = start_time + timedelta(minutes=duration_minutes)
        return ParkingSession(
            provider=self.name,
            session_id=str(data.get("sessionId") or r.headers.get("Location", "?")),
            vehicle_plate=vehicle_plate,
            location_id=location_id,
            start=start_time,
            end=end_time,
            amount_cents=int(data.get("totalCost", {}).get("amount", 0) * 100),
        )

    def get_active_session(self, vehicle_plate: str) -> ParkingSession | None:
        if self.dry_run:
            return None
        if not self._account_id:
            return None
        r = self._client.get(
            f"{self.base_url}/parking/accounts/{self._account_id}/sessions/current"
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        # Filtre sur la plaque
        for s in data if isinstance(data, list) else [data]:
            if s.get("licensePlate") == vehicle_plate:
                return ParkingSession(
                    provider=self.name,
                    session_id=str(s["sessionId"]),
                    vehicle_plate=vehicle_plate,
                    location_id=s.get("locationId", "?"),
                    start=datetime.fromisoformat(s["startTime"]),
                    end=datetime.fromisoformat(s["expireTime"]),
                    amount_cents=int(s.get("totalCost", {}).get("amount", 0) * 100),
                )
        return None
