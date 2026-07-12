"""Computer-vision CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from boring.benchmark import run_vision_benchmark
from boring.benchmark import write_report as write_benchmark_report
from boring.capture import iter_frames
from boring.detect import Detector
from boring.vision_eval import evaluate_yolo_dataset
from boring.vision_eval import write_report as write_vision_eval_report
from boring.vision_readiness import audit_vision_readiness
from boring.vision_readiness import write_report as write_vision_readiness_report
from boring.vision_sources import load_source_catalog


def register_vision_commands(app: typer.Typer, console: Console) -> None:
    @app.command("vision-ready")
    def vision_ready(
        dataset: Path = typer.Option(
            Path("datasets/control_vehicle_v1"),
            help="Dossier YOLOv8 exporte par Roboflow.",
        ),
        model: Path = typer.Option(Path("models/best.pt"), help="Modele fine-tune attendu."),
        baseline_manifest: Path = typer.Option(
            Path("datasets/baseline/manifest.jsonl"),
            help="Manifest des images web gratuites scrapees.",
        ),
        source_catalog: Path = typer.Option(
            Path("data/vision_free_sources.json"),
            help="Catalogue JSON des sources gratuites candidates.",
        ),
        output: Path = typer.Option(Path("reports/vision-readiness.json"), help="Rapport JSON."),
        require_edge_export: bool = typer.Option(
            False,
            help="Exiger best.onnx ou best.tflite pour Pi/edge.",
        ),
        allow_unreviewed_sources: bool = typer.Option(
            False,
            help="Ne pas exiger la revue licence des images baseline.",
        ),
    ) -> None:
        """Audite dataset, modele et exports edge avant integration boitier."""
        report = audit_vision_readiness(
            dataset_path=dataset,
            model_path=model,
            baseline_manifest=baseline_manifest,
            source_catalog=source_catalog,
            require_edge_export=require_edge_export,
            require_license_review=not allow_unreviewed_sources,
        )
        write_vision_readiness_report(report, output)
        table = Table(title="Computer vision readiness")
        table.add_column("Check", style="bold")
        table.add_column("Status")
        table.add_column("Detail")
        for check in report.checks:
            table.add_row(check.name, "OK" if check.ok else "FAIL", check.detail)
        table.add_row("passed", "yes" if report.passed else "no", str(output))
        console.print(table)
        raise typer.Exit(0 if report.passed else 1)

    @app.command("vision-sources")
    def vision_sources(
        source_catalog: Path = typer.Option(
            Path("data/vision_free_sources.json"),
            help="Catalogue JSON des sources gratuites candidates.",
        ),
    ) -> None:
        """Affiche les sources gratuites candidates pour le dataset vision."""
        catalog = load_source_catalog(source_catalog)
        table = Table(title="Computer vision free sources")
        table.add_column("Source", style="bold")
        table.add_column("Usage")
        table.add_column("Policy")
        table.add_column("Action")
        for source in catalog.sources:
            table.add_row(
                source.name,
                ",".join(source.usage),
                source.train_policy,
                source.action,
            )
        console.print(table)

    @app.command("vision-benchmark")
    def vision_benchmark(
        model: Path = typer.Option(Path("models/best.pt"), help="Modele a benchmarker."),
        target: str = typer.Option("control_vehicle", help="Labels cibles, separes par virgule."),
        device: str = typer.Option("cpu", help="cpu / cuda / mps / auto."),
        camera: int = typer.Option(0, help="Index camera."),
        frames: int = typer.Option(120, help="Nombre de frames a inferer."),
        min_fps: float = typer.Option(1.0, help="FPS minimal acceptable."),
        confidence: float = typer.Option(0.5, help="Seuil de confiance."),
        output: Path = typer.Option(
            Path("reports/vision-benchmark.json"),
            help="Rapport JSON.",
        ),
    ) -> None:
        """Mesure le debit d'inference reel sur le hardware cible."""
        labels = tuple(label.strip() for label in target.split(",") if label.strip())
        detector = Detector(
            model_path=model,
            target_labels=labels or ("control_vehicle",),
            confidence_threshold=confidence,
            device=device,
        )
        report = run_vision_benchmark(
            detector=detector,
            frames=iter_frames(device_index=camera, fps=None),
            model_path=str(model),
            target_labels=labels or ("control_vehicle",),
            device=device,
            min_fps=min_fps,
            max_frames=frames,
        )
        write_benchmark_report(report, output)
        table = Table(title="Computer vision benchmark")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Frames", str(report.frames_processed))
        table.add_row("Detections", str(report.detections_seen))
        table.add_row("Duration", f"{report.duration_seconds:.2f}s")
        table.add_row("Measured FPS", f"{report.measured_fps:.2f}")
        table.add_row("Min FPS", f"{report.min_fps:.2f}")
        table.add_row("Passed", "yes" if report.passed else "no")
        console.print(table)
        console.print(f"[dim]Rapport: {output}[/dim]")
        raise typer.Exit(0 if report.passed else 1)

    @app.command("vision-eval")
    def vision_eval(
        dataset: Path = typer.Option(
            Path("datasets/control_vehicle_v1"),
            help="Dossier YOLOv8 a evaluer.",
        ),
        model: Path = typer.Option(Path("models/best.pt"), help="Modele fine-tune."),
        dataset_id: str = typer.Option("field-validation-v1", help="Identifiant du set evalue."),
        split: str = typer.Option("valid", help="Split YOLO a evaluer."),
        target: str = typer.Option("control_vehicle", help="Classe cible."),
        device: str = typer.Option("cpu", help="cpu / cuda / mps / auto."),
        confidence: float = typer.Option(0.5, help="Seuil de confiance."),
        frame_interval: float = typer.Option(
            1.0,
            help="Secondes representees par chaque image extraite.",
        ),
        min_recall: float = typer.Option(0.90, help="Recall minimal acceptable."),
        max_fp_per_hour: float = typer.Option(1.0, help="Faux positifs max par heure."),
        output: Path = typer.Option(Path("reports/vision-eval.json"), help="Rapport JSON."),
    ) -> None:
        """Evalue le modele sur un split YOLO et produit reports/vision-eval.json."""
        detector = Detector(
            model_path=model,
            target_labels=(target,),
            confidence_threshold=confidence,
            device=device,
        )
        report = evaluate_yolo_dataset(
            detector=detector,
            dataset_path=dataset,
            model_path=str(model),
            dataset_id=dataset_id,
            split=split,
            required_class=target,
            frame_interval_seconds=frame_interval,
            min_recall=min_recall,
            max_false_positive_per_hour=max_fp_per_hour,
        )
        write_vision_eval_report(report, output)
        table = Table(title="Computer vision eval")
        table.add_column("Metric", style="bold")
        table.add_column("Value")
        table.add_row("Frames", str(report.frames_evaluated))
        table.add_row(
            "TP / FP / FN",
            f"{report.true_positives} / {report.false_positives} / {report.false_negatives}",
        )
        table.add_row("Recall", f"{report.recall:.3f} / min {report.min_recall:.3f}")
        table.add_row("Precision", f"{report.precision:.3f}")
        table.add_row(
            "FP/hour",
            f"{report.false_positive_per_hour:.2f} / max {report.max_false_positive_per_hour:.2f}",
        )
        table.add_row("Evaluated hours", f"{report.evaluated_hours:.2f}")
        table.add_row("Invalid images", str(report.invalid_images))
        table.add_row("Passed", "yes" if report.passed else "no")
        console.print(table)
        console.print(f"[dim]Rapport: {output}[/dim]")
        raise typer.Exit(0 if report.passed else 1)
