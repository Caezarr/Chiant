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
import datetime
import json
import re
import sys
import urllib.parse
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


def _parse_form_body(text: str) -> dict[str, str]:
    """Parse une chaîne form-urlencoded en dict."""
    try:
        return dict(urllib.parse.parse_qsl(text, keep_blank_values=True))
    except Exception:
        return {}


def _parse_body_raw(text: str | None) -> dict:
    """Parse le body brut (JSON ou form-urlencoded) sans masquage."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    return _parse_form_body(text)


def extract_config_hints(records: list[dict]) -> dict:
    """Analyse les records HAR et extrait les hints de configuration.

    Retourne un dict avec les clés suivantes (valeur None si non trouvé) :
    - base_url, auth_url, client_id, account_id, rate_option_id, payment_method_id
    """
    hints: dict[str, str | None] = {
        "base_url": None,
        "auth_url": None,
        "client_id": None,
        "account_id": None,
        "rate_option_id": None,
        "payment_method_id": None,
    }

    # base_url : domaine commun (scheme + host) de la 1re requête PayByPhone
    for rec in records:
        url = rec.get("url", "")
        if url:
            parsed = urllib.parse.urlparse(url)
            hints["base_url"] = f"{parsed.scheme}://{parsed.netloc}"
            break

    # Patterns pour account_id dans les URLs de session
    account_session_re = re.compile(
        r"/parking/accounts/([^/]+)/sessions", re.I
    )

    for rec in records:
        url = rec.get("url", "")
        method = (rec.get("method") or "").upper()
        body_text = rec.get("request_body")

        # body brut — on le re-parse sans masquage depuis rec car request_body est déjà scrubbed;
        # on l'utilise quand même (client_id n'est pas maskable, rate/payment ids ne le sont pas non plus)
        body = _parse_body_raw(body_text)

        # auth_url + client_id : POST avec grant_type=password
        if method == "POST" and (
            body.get("grant_type") == "password"
            or "grant_type=password" in (body_text or "")
        ):
            if hints["auth_url"] is None:
                hints["auth_url"] = url
            if hints["client_id"] is None:
                hints["client_id"] = body.get("client_id") or _parse_form_body(
                    body_text or ""
                ).get("client_id")

        # account_id depuis URL sessions
        if hints["account_id"] is None:
            m = account_session_re.search(url)
            if m:
                hints["account_id"] = m.group(1)

        # rate_option_id + payment_method_id depuis POST de démarrage de session
        if method == "POST" and account_session_re.search(url):
            if hints["rate_option_id"] is None:
                hints["rate_option_id"] = body.get("rateOptionId") or body.get(
                    "rate_option_id"
                )
            if hints["payment_method_id"] is None:
                hints["payment_method_id"] = body.get("paymentMethodId") or body.get(
                    "payment_method_id"
                )

    return hints


def _summarize_hints(hints: dict) -> None:
    """Affiche dans la console ce qui a été extrait et ce qui manque."""
    console.print("\n[bold]Config hints extraits :[/bold]")
    for key, value in hints.items():
        if value is not None:
            console.print(f"  [green]{key}[/green] : {value}")
        else:
            console.print(f"  [yellow]{key} : non trouvé[/yellow]")


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


def _patch_env(hints: dict, env_path: Path) -> None:
    """Ajoute les variables d'environnement au fichier .env."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"\n# Auto-patch depuis HAR — {timestamp}\n"]
    mapping = {
        "PAYBYPHONE_API_BASE": hints.get("base_url"),
        "PAYBYPHONE_AUTH_URL": hints.get("auth_url"),
        "PAYBYPHONE_CLIENT_ID": hints.get("client_id"),
    }
    for var, val in mapping.items():
        if val is not None:
            lines.append(f"{var}={val}\n")

    with env_path.open("a") as f:
        f.writelines(lines)
    console.print(f"\n[green]✓[/green] .env patché : {env_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("har", type=Path, help="Chemin vers le fichier .har")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("scripts/paybyphone_endpoints.json"),
        help="Sortie JSON.",
    )
    parser.add_argument(
        "--patch-env",
        action="store_true",
        default=False,
        help="Ajoute les variables extraites au fichier .env du projet.",
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

    hints = extract_config_hints(records)
    output = {"config_hints": hints, "requests": records}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False))

    summarize(records)
    _summarize_hints(hints)

    console.print(f"\n[green]✓[/green] {len(records)} requêtes → {args.out}")

    if args.patch_env:
        env_path = Path(".env")
        _patch_env(hints, env_path)

    console.print(
        "\n[bold]Envoie ce fichier (credentials déjà masqués) pour finaliser le client.[/bold]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
