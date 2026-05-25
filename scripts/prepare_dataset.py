"""Échantillonne des frames depuis des vidéos brutes pour annotation Roboflow.

Workflow Phase 2 :
1. Filme à Lille avec ton iPhone → mets les .mov dans datasets/raw/
2. python scripts/prepare_dataset.py → extrait 1 frame/seconde dans datasets/extracted/
3. Upload datasets/extracted/ sur Roboflow, annote 'scan_car'
4. Roboflow exporte en format YOLOv8 → datasets/scan_car_v1/
5. uv run yolo train data=datasets/scan_car_v1/data.yaml model=yolov8n.pt epochs=50
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
from rich.console import Console

console = Console()

RAW_DIR = Path("datasets/raw")
OUTPUT_DIR = Path("datasets/extracted")
TARGET_FPS = 1.0


def extract(video_path: Path) -> int:
    cap = cv2.VideoCapture(str(video_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    every_n = int(src_fps / TARGET_FPS) or 1
    n_extracted = 0
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % every_n == 0:
            out = OUTPUT_DIR / f"{video_path.stem}_{idx:06d}.jpg"
            cv2.imwrite(str(out), frame)
            n_extracted += 1
        idx += 1
    cap.release()
    return n_extracted


def main() -> int:
    if not RAW_DIR.exists() or not any(RAW_DIR.iterdir()):
        console.print(f"[red]Aucune vidéo dans {RAW_DIR}.[/red]")
        console.print("Mets tes captations Lille (.mov/.mp4) puis relance.")
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for video in sorted(RAW_DIR.iterdir()):
        if video.suffix.lower() not in (".mp4", ".mov", ".m4v"):
            continue
        n = extract(video)
        console.print(f"[green]✓[/green] {video.name} → {n} frames")
        total += n
    console.print(f"\n[bold]Total : {total} frames dans {OUTPUT_DIR}[/bold]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
