"""Local maintainability audit for CTO/dev handoff checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from boring.payment import PROVIDER_REGISTRY
from boring.payment.stub import DryRunParkingProvider

BIG_FILE_LINE_THRESHOLD = 1_000
FIELD_ARTIFACTS = (
    Path("datasets/control_vehicle_v1/data.yaml"),
    Path("models/best.pt"),
    Path("models/best.onnx"),
    Path("scripts/paybyphone_endpoints.json"),
    Path("reports/vision-eval.json"),
    Path("reports/vision-benchmark.json"),
    Path("reports/autopay-smoke.json"),
    Path("reports/box-readiness.json"),
    Path("burn-in/report.json"),
    Path("burn-in/samples.jsonl"),
)


@dataclass(frozen=True)
class CodeAuditReport:
    big_files: list[tuple[str, int]]
    stub_providers: list[str]
    missing_field_artifacts: list[str]
    test_files: int

    @property
    def warning_count(self) -> int:
        return len(self.big_files) + len(self.stub_providers) + len(self.missing_field_artifacts)


def run_code_audit(project_root: Path = Path(".")) -> CodeAuditReport:
    root = project_root.resolve()
    line_counts = [
        (str(path.relative_to(root)), _line_count(path))
        for path in (root / "src" / "boring").rglob("*.py")
    ]
    big_files = sorted(
        (item for item in line_counts if item[1] > BIG_FILE_LINE_THRESHOLD),
        key=lambda item: item[1],
        reverse=True,
    )
    stub_providers = sorted(
        name
        for name, provider_cls in PROVIDER_REGISTRY.items()
        if issubclass(provider_cls, DryRunParkingProvider)
        and getattr(provider_cls, "integration_status", "") == "stub"
    )
    missing_field_artifacts = [str(path) for path in FIELD_ARTIFACTS if not (root / path).exists()]
    test_files = len(list((root / "tests").glob("test_*.py")))
    return CodeAuditReport(
        big_files=big_files,
        stub_providers=stub_providers,
        missing_field_artifacts=missing_field_artifacts,
        test_files=test_files,
    )


def _line_count(path: Path) -> int:
    return len(path.read_text().splitlines())
