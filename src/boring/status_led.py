"""LED d'etat du boitier (une LED sur un GPIO).

La LED ne doit jamais faire tomber le service : si le GPIO ou gpiozero est
indisponible, le pilote se desactive et le runtime continue.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Protocol


class LedState(str, Enum):
    OFF = "off"
    STARTING = "starting"
    ACTIVE = "active"
    WARNING = "warning"
    ERROR = "error"


# (allume, eteint) en secondes. ACTIVE = bref eclat toutes les 3 s : visible
# quand on le cherche, discret de nuit.
LED_PATTERNS: dict[LedState, tuple[float, float]] = {
    LedState.STARTING: (0.5, 0.5),
    LedState.ACTIVE: (0.05, 2.95),
    LedState.WARNING: (0.2, 0.8),
    LedState.ERROR: (0.1, 0.1),
}


class LedDevice(Protocol):
    def blink(self, on_time: float, off_time: float) -> None: ...

    def off(self) -> None: ...

    def close(self) -> None: ...


def _gpiozero_led(pin: int, active_high: bool) -> LedDevice:
    from gpiozero import LED  # type: ignore[import-not-found]

    return LED(pin, active_high=active_high)


class StatusLed:
    def __init__(self, device: LedDevice | None) -> None:
        self._device = device
        self._state = LedState.OFF

    @property
    def enabled(self) -> bool:
        return self._device is not None

    @property
    def state(self) -> LedState:
        return self._state

    def set(self, state: LedState) -> None:
        if state == self._state:
            return
        self._state = state
        if self._device is None:
            return
        try:
            if state is LedState.OFF:
                self._device.off()
            else:
                on_time, off_time = LED_PATTERNS[state]
                self._device.blink(on_time, off_time)
        except Exception:
            self._device = None

    def close(self) -> None:
        device, self._device = self._device, None
        self._state = LedState.OFF
        if device is None:
            return
        try:
            device.off()
            device.close()
        except Exception:
            pass


def make_status_led(
    pin: int | None,
    active_high: bool = True,
    device_factory: Callable[[int, bool], LedDevice] = _gpiozero_led,
    on_error: Callable[[str], Any] | None = None,
) -> StatusLed:
    """Cree la LED d'etat. ``pin=None`` ou GPIO indisponible = LED desactivee."""
    if pin is None:
        return StatusLed(None)
    try:
        return StatusLed(device_factory(pin, active_high))
    except Exception as exc:
        if on_error is not None:
            on_error(str(exc))
        return StatusLed(None)
