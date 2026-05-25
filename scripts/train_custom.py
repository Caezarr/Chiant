"""Lance le fine-tuning YOLOv8n sur un dataset Roboflow exporté.

Usage :
    1. Tu télécharges depuis Roboflow le dataset au format "YOLOv8" → zip
    2. Tu décompresses dans datasets/<nom>/ — doit contenir data.yaml + train/ valid/
    3. uv run python scripts/train_custom.py --data datasets/<nom>/data.yaml

Hyperparamètres calés pour Apple Silicon (MPS). Sortie : models/best.pt.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from rich.console import Console
from ultralytics import YOLO

console = Console()

DEFAULT_BASE_MODEL = "yolov8n.pt"
DEFAULT_EPOCHS = 80
DEFAULT_BATCH = 16
DEFAULT_IMGSZ = 640
OUTPUT_DIR = Path("models")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fine-tune YOLOv8n sur dataset custom.")
    parser.add_argument("--data", required=True, help="Chemin vers data.yaml Roboflow.")
    parser.add_argument("--base", default=DEFAULT_BASE_MODEL, help="Modèle de base.")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--device", default="mps", help="mps (Apple) / cuda / cpu")
    parser.add_argument("--name", default="custom_v1", help="Nom du run.")
    args = parser.parse_args()

    data_yaml = Path(args.data)
    if not data_yaml.exists():
        console.print(f"[red]Fichier data.yaml introuvable : {data_yaml}[/red]")
        console.print("Décompresse l'export Roboflow dans datasets/ et pointe vers son data.yaml.")
        return 1

    console.print(f"[bold]Fine-tuning {args.base}[/bold] sur {data_yaml}")
    console.print(
        f"epochs={args.epochs} batch={args.batch} imgsz={args.imgsz} device={args.device}"
    )

    model = YOLO(args.base)
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        name=args.name,
        patience=15,  # early stopping si pas d'amélioration
        save_period=10,
    )

    # Copie le best.pt dans models/ pour utilisation directe
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    src_best = Path("runs/detect") / args.name / "weights" / "best.pt"
    if src_best.exists():
        dst = OUTPUT_DIR / "best.pt"
        shutil.copy2(src_best, dst)
        console.print(f"[green]✓ Modèle copié : {dst}[/green]")
        console.print(
            "\n[bold]Pour l'utiliser :[/bold]\n"
            f"  uv run boring detect --model {dst} --target control_vehicle\n"
        )
    else:
        console.print(f"[yellow]⚠ best.pt non trouvé à {src_best}[/yellow]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
