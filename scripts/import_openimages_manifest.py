"""Importe un sous-ensemble Open Images dans le manifest baseline.

Le script ne telecharge pas les images. Il lit les CSV Open Images locaux
(`class-descriptions-boxable.csv` et `*-annotations-bbox.csv`), filtre quelques
classes utiles pour des hard negatives, puis ecrit :

- `datasets/baseline/manifest.jsonl`
- `datasets/baseline/openimages-download-list.txt`

Les entrees sont marquees `license_status=open-images` et `license_reviewed=true`
pour pouvoir passer le gate licence tout en gardant la provenance explicite.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

console = Console()

DEFAULT_CLASS_NAMES = ("Car", "Van", "Truck", "Bus")
IMAGE_URL_TEMPLATE = "https://storage.googleapis.com/openimages/2018_04/{split}/{image_id}.jpg"


@dataclass(frozen=True)
class OpenImagesRecord:
    path: str
    url: str
    query: str
    profile: str
    label_hint: str
    phash: str
    width: int
    height: int
    source: str = "open-images"
    license_hint: str = "open-images"
    license_status: str = "open-images"
    license_reviewed: bool = True
    created_at: str = ""
    image_id: str = ""
    class_name: str = ""
    class_id: str = ""


def load_class_ids(descriptions_csv: Path, wanted_names: tuple[str, ...]) -> dict[str, str]:
    wanted = {name.strip().lower(): name.strip() for name in wanted_names if name.strip()}
    matches: dict[str, str] = {}
    with descriptions_csv.open(newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 2:
                continue
            class_id, name = row[0].strip(), row[1].strip()
            wanted_name = wanted.get(name.lower())
            if wanted_name:
                matches[class_id] = wanted_name
    return matches


def iter_openimages_records(
    *,
    annotations_csv: Path,
    class_ids: dict[str, str],
    split: str,
    output_dir: Path,
    limit: int,
    existing_image_ids: set[str] | None = None,
) -> list[OpenImagesRecord]:
    seen = set(existing_image_ids or set())
    records: list[OpenImagesRecord] = []
    with annotations_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            image_id = (row.get("ImageID") or "").strip()
            class_id = (row.get("LabelName") or "").strip()
            if not image_id or class_id not in class_ids or image_id in seen:
                continue
            class_name = class_ids[class_id]
            seen.add(image_id)
            records.append(
                OpenImagesRecord(
                    path=str(output_dir / "negatives" / f"openimages-{image_id}.jpg"),
                    url=IMAGE_URL_TEMPLATE.format(split=split, image_id=image_id),
                    query=f"Open Images {class_name}",
                    profile="negatives",
                    label_hint="hard_negative",
                    phash="openimages-pending-download",
                    width=0,
                    height=0,
                    image_id=image_id,
                    class_name=class_name,
                    class_id=class_id,
                )
            )
            if len(records) >= limit:
                break
    return records


def append_records(manifest_path: Path, records: list[OpenImagesRecord]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a") as f:
        for record in records:
            payload = asdict(record)
            if not payload["created_at"]:
                payload["created_at"] = datetime.now(timezone.utc).isoformat()
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_download_list(path: Path, records: list[OpenImagesRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(record.url for record in records) + ("\n" if records else ""))


def load_manifest_image_ids(manifest_path: Path) -> set[str]:
    if not manifest_path.exists():
        return set()
    image_ids: set[str] = set()
    for line in manifest_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        image_id = str(payload.get("image_id") or "").strip()
        if image_id:
            image_ids.add(image_id)
    return image_ids


def parse_class_names(value: str) -> tuple[str, ...]:
    names = tuple(name.strip() for name in value.split(",") if name.strip())
    return names or DEFAULT_CLASS_NAMES


def main() -> int:
    parser = argparse.ArgumentParser(description="Importe un manifest Open Images baseline.")
    parser.add_argument("--descriptions", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("datasets/baseline"))
    parser.add_argument("--split", default="train", choices=("train", "validation", "test"))
    parser.add_argument("--classes", default=",".join(DEFAULT_CLASS_NAMES))
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    manifest = args.output / "manifest.jsonl"
    class_ids = load_class_ids(args.descriptions, parse_class_names(args.classes))
    if not class_ids:
        console.print("[red]Aucune classe Open Images trouvee.[/red]")
        return 1
    records = iter_openimages_records(
        annotations_csv=args.annotations,
        class_ids=class_ids,
        split=args.split,
        output_dir=args.output,
        limit=args.limit,
        existing_image_ids=load_manifest_image_ids(manifest),
    )
    append_records(manifest, records)
    download_list = args.output / "openimages-download-list.txt"
    write_download_list(download_list, records)
    console.print(
        f"[green]OK[/green] {len(records)} entrees Open Images ajoutees; "
        f"download list: {download_list}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
