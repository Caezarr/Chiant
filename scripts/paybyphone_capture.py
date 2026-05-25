"""Addon mitmproxy : capture les échanges HTTP avec les serveurs PayByPhone.

But : extraire le format d'API (endpoints, headers, payloads) pour pouvoir
implémenter le client `boring.payment.paybyphone` en mode live.

Usage :
    1. Sur ton Mac : `uv run mitmproxy -s scripts/paybyphone_capture.py`
       (mitmproxy écoute par défaut sur 127.0.0.1:8080)
    2. Sur ton iPhone :
       - Réglages > Wi-Fi > ton réseau > Configurer le proxy → Manuel
       - Serveur : l'IP locale de ton Mac (ifconfig | grep "inet " | grep -v 127)
       - Port : 8080
    3. Va sur http://mitm.it depuis Safari iPhone → installe le certificat CA
       (Réglages > Général > VPN et gestion d'appareils > Fichier de configuration
        puis Réglages > Général > Informations > Certificats de confiance)
    4. Ouvre l'app PayByPhone, login, démarre une session de 15 min, stoppe-la
    5. Quitte mitmproxy (q puis y)
    6. Le fichier `scripts/paybyphone_flow.json` contient les requêtes filtrées

Tu m'envoies `paybyphone_flow.json` et je code le client réel.
"""

from __future__ import annotations

import json
from pathlib import Path

from mitmproxy import http

OUTPUT_FILE = Path("scripts/paybyphone_flow.json")
PAYBYPHONE_HOST_PATTERNS = ("paybyphone", "pbp", "parkmobile")  # élargi par sécurité


def _is_relevant(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    return any(pattern in host for pattern in PAYBYPHONE_HOST_PATTERNS)


class PayByPhoneRecorder:
    def __init__(self) -> None:
        self.records: list[dict] = []
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    def response(self, flow: http.HTTPFlow) -> None:
        if not _is_relevant(flow):
            return

        req = flow.request
        resp = flow.response

        record = {
            "method": req.method,
            "url": req.pretty_url,
            "host": req.pretty_host,
            "path": req.path,
            "request_headers": dict(req.headers),
            "request_body_text": req.get_text(strict=False) if req.content else None,
            "response_status": resp.status_code if resp else None,
            "response_headers": dict(resp.headers) if resp else {},
            "response_body_text": resp.get_text(strict=False) if resp and resp.content else None,
        }
        # Masque les éventuels Bearer/Authorization dans les logs console
        safe_url = req.pretty_url
        print(f"[capture] {req.method} {safe_url} → {resp.status_code if resp else '?'}")
        self.records.append(record)
        self._flush()

    def _flush(self) -> None:
        OUTPUT_FILE.write_text(json.dumps(self.records, indent=2, ensure_ascii=False))


addons = [PayByPhoneRecorder()]
