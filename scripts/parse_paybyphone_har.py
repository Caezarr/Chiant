"""Parse un fichier HAR exporté depuis Safari/Chrome DevTools et extrait
les appels API PayByPhone pertinents pour valider/raffiner le client.

Workflow Gabriel (10 min) :
1. Sur Mac, ouvre https://m.paybyphone.fr dans Safari (ou Chrome)
2. Ouvre les DevTools : Cmd-Option-I (Safari) ou Cmd-Option-J (Chrome)
3. Onglet Network → coche "Preserve log" → vide la liste
4. Login PayByPhone sur le site
5. Démarre une session de stationnement 15 min (à un endroit réel de Lille)
6. Vérifie que la session est active, puis stop la session
7. Clic droit dans Network → "Save All As HAR" → enregistre en `scripts/pbp.har`
8. Lance : uv run python scripts/parse_paybyphone_har.py scripts/pbp.har
9. M'envoie scripts/paybyphone_endpoints.json

Le script masque automatiquement les credentials/tokens dans la sortie.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()

# Domaines PayByPhone connus — élargi par sécurité
PAYBYPHONE_HOST_PATTERN = re.compile(r"paybyphone|pbp\.com|m\.pbp|api\.pbp", re.I)

# Headers à masquer dans le rapport (case-insensitive)
SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-csrf-token",
    "x-auth-token",
}

# Champs body à masquer
SENSITIVE_BODY_KEYS = {"password", "cvv", "cvc", "client_secret", "refresh_token"}


def _mask(value: str) -> str:
    if not value or len(value) < 8:
        return "***"
    return f"{value[:4]}…{value[-3:]}"


def _scrub_headers(headers: list[dict]) -> list[dict]:
    out = []
    for h in headers:
        name = h.get("name", "")
        value = h.get("value", "")
        if name.lower() in SENSITIVE_HEADERS:
            value = _mask(value)
        out.append({"name": name, "value": value})
    return out


def _scrub_body(text: str | None) -> str | None:
    if not text:
        return text
    # Tente JSON
    try:
        data = json.loads(text)
        return json.dumps(_scrub_json(data), ensure_ascii=False)
    except (ValueError, TypeError):
        pass
    # Form-urlencoded
    for key in SENSITIVE_BODY_KEYS:
        text = re.sub(rf"({key}=)[^&]+", r"\1***", text, flags=re.I)
    return text


def _scrub_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("***" if k.lower() in SENSITIVE_BODY_KEYS else _scrub_json(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_scrub_json(item) for item in obj]
    return obj


def parse_har(har_path: Path) -> list[dict]:
    har = json.loads(har_path.read_text())
    entries = har.get("log", {}).get("entries", [])
    out = []
    for e in entries:
        req = e.get("request", {})
        resp = e.get("response", {})
        url = req.get("url", "")
        if not PAYBYPHONE_HOST_PATTERN.search(url):
            continue
        rec = {
            "method": req.get("method"),
            "url": url,
            "request_headers": _scrub_headers(req.get("headers", [])),
            "request_body": _scrub_body((req.get("postData") or {}).get("text")),
            "response_status": resp.get("status"),
            "response_headers": _scrub_headers(resp.get("headers", [])),
            "response_body": _scrub_body((resp.get("content") or {}).get("text")),
        }
        out.append(rec)
    return out


def summarize(records: list[dict]) -> None:
    table = Table(title=f"PayByPhone API calls ({len(records)} requêtes)")
    table.add_column("#", justify="right")
    table.add_column("Method")
    table.add_column("Status")
    table.add_column("URL", overflow="fold")
    for i, r in enumerate(records, 1):
        status = str(r["response_status"]) if r["response_status"] else "?"
        color = "green" if r["response_status"] and r["response_status"] < 400 else "red"
        table.add_row(str(i), r["method"], f"[{color}]{status}[/{color}]", r["url"])
    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("har", type=Path, help="Chemin vers le fichier .har")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("scripts/paybyphone_endpoints.json"),
        help="Sortie JSON.",
    )
    args = parser.parse_args()
    if not args.har.exists():
        console.print(f"[red]Fichier introuvable : {args.har}[/red]")
        return 1
    records = parse_har(args.har)
    if not records:
        console.print(
            "[yellow]Aucune requête PayByPhone trouvée dans ce HAR. "
            "Vérifie que tu as bien fait le flow login + session sur m.paybyphone.fr.[/yellow]"
        )
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    summarize(records)
    console.print(f"\n[green]✓[/green] {len(records)} requêtes → {args.out}")
    console.print(
        "\n[bold]Envoie ce fichier (credentials déjà masqués) pour finaliser le client.[/bold]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
