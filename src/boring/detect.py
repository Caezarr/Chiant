"""Détection YOLOv8 + tracker anti-faux-positif sur flux live."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
from rich.console import Console
from ultralytics import YOLO

from boring.capture import iter_frames

console = Console()

DEFAULT_MODEL = "yolov8n.pt"


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple[int, int, int, int]
    timestamp: float


class Detector:
    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL,
        target_labels: tuple[str, ...] = ("car",),
        confidence_threshold: float = 0.5,
        device: str = "auto",
    ) -> None:
        console.print(f"[dim]Chargement modèle {model_path} sur {device}…[/dim]")
        self.model = YOLO(str(model_path))
        self.target_labels = target_labels
        self.confidence_threshold = confidence_threshold
        self.device = device

    def detect_frame(self, frame, timestamp: float) -> list[Detection]:
        kwargs = {"verbose": False, "conf": self.confidence_threshold}
        if self.device != "auto":
            kwargs["device"] = self.device
        results = self.model.predict(frame, **kwargs)
        out: list[Detection] = []
        for r in results:
            names = r.names
            for box in r.boxes:
                label = names[int(box.cls)]
                if label not in self.target_labels:
                    continue
                conf = float(box.conf)
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                out.append(
                    Detection(
                        label=label,
                        confidence=conf,
                        bbox=(x1, y1, x2, y2),
                        timestamp=timestamp,
                    )
                )
        return out


class StreamTracker:
    """Ne déclenche qu'après N détections dans une fenêtre temporelle."""

    def __init__(self, required_consecutive: int = 3, window_seconds: float = 2.0) -> None:
        self.required_consecutive = required_consecutive
        self.window_seconds = window_seconds
        self.recent: deque[float] = deque()

    def update(self, has_detection: bool, timestamp: float) -> bool:
        if not has_detection:
            self.recent.clear()
            return False
        while self.recent and timestamp - self.recent[0] > self.window_seconds:
            self.recent.popleft()
        self.recent.append(timestamp)
        return len(self.recent) >= self.required_consecutive


class AdaptiveFrameGate:
    """Filtre les frames pour respecter un FPS qui peut changer au runtime."""

    def __init__(self) -> None:
        self.last_emit: float | None = None

    def allow(self, timestamp: float, fps: float) -> bool:
        if fps <= 0:
            return False
        if self.last_emit is None:
            self.last_emit = timestamp
            return True
        interval = 1.0 / fps
        if timestamp - self.last_emit >= interval:
            self.last_emit = timestamp
            return True
        return False


def _annotate(frame, detections: list[Detection], triggered: bool) -> None:
    color = (0, 0, 255) if triggered else (0, 255, 0)
    for d in detections:
        x1, y1, x2, y2 = d.bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            f"{d.label} {d.confidence:.2f}",
            (x1, y1 - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )
    if triggered:
        cv2.putText(frame, "TRIGGER", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)


def run_live_detection(
    detector: Detector,
    fps: float = 5.0,
    show_window: bool = True,
    tracker: StreamTracker | None = None,
    device_index: int = 0,
    fps_provider: Callable[[], float] | None = None,
) -> Iterator[list[Detection]]:
    """Boucle live, yield à chaque trigger (détection consécutive franchie)."""
    tracker = tracker or StreamTracker()
    frame_gate = AdaptiveFrameGate() if fps_provider is not None else None
    capture_fps = None if fps_provider is not None else fps
    for ts, frame in iter_frames(device_index=device_index, fps=capture_fps):
        if frame_gate is not None and not frame_gate.allow(ts, fps_provider()):
            continue
        detections = detector.detect_frame(frame, ts)
        triggered = tracker.update(bool(detections), ts)

        if show_window:
            _annotate(frame, detections, triggered)
            cv2.imshow("Boring — detect (Q to quit)", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break

        if triggered:
            yield detections

    cv2.destroyAllWindows()
