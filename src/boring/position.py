"""Providers de position pour la box."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    lat: float
    lon: float
    source: str


class PositionProvider:
    def current(self) -> Position | None:
        raise NotImplementedError


class StaticPositionProvider(PositionProvider):
    def __init__(self, lat: float | None, lon: float | None) -> None:
        self.lat = lat
        self.lon = lon

    def current(self) -> Position | None:
        if self.lat is None or self.lon is None:
            return None
        return Position(lat=self.lat, lon=self.lon, source="static")


class GpsdPositionProvider(PositionProvider):
    """Lit une position TPV depuis gpsd sans dependance Python externe."""

    def __init__(self, host: str = "127.0.0.1", port: int = 2947, timeout_seconds: float = 3.0):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def current(self) -> Position | None:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            ) as sock:
                sock.settimeout(self.timeout_seconds)
                sock.sendall(b'?WATCH={"enable":true,"json":true};\n')
                for _ in range(10):
                    chunk = sock.recv(4096).decode("utf-8", errors="ignore")
                    for raw in chunk.splitlines():
                        if position := parse_gpsd_tpv(raw):
                            return position
        except OSError:
            return None
        return None


def parse_gpsd_tpv(raw: str) -> Position | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if payload.get("class") != "TPV":
        return None
    lat = payload.get("lat")
    lon = payload.get("lon")
    if lat is None or lon is None:
        return None
    return Position(lat=float(lat), lon=float(lon), source="gpsd")


def make_position_provider(
    mode: str,
    lat: float | None,
    lon: float | None,
    gpsd_host: str = "127.0.0.1",
    gpsd_port: int = 2947,
) -> PositionProvider:
    if mode == "gpsd":
        return GpsdPositionProvider(gpsd_host, gpsd_port)
    return StaticPositionProvider(lat, lon)
