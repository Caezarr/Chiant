from __future__ import annotations

from boring.runtime import RuntimeState, led_state_for
from boring.status_led import LED_PATTERNS, LedState, StatusLed, make_status_led


def test_led_disabled_without_pin():
    led = make_status_led(None)

    led.set(LedState.ACTIVE)

    assert led.enabled is False
    assert led.state is LedState.ACTIVE


def test_led_blinks_pattern_once_per_state_change():
    device = _FakeLed()
    led = make_status_led(17, device_factory=lambda pin, active_high: device)

    led.set(LedState.STARTING)
    led.set(LedState.STARTING)
    led.set(LedState.ACTIVE)
    led.set(LedState.OFF)

    assert device.calls == [
        ("blink", *LED_PATTERNS[LedState.STARTING]),
        ("blink", *LED_PATTERNS[LedState.ACTIVE]),
        ("off",),
    ]


def test_led_factory_failure_disables_led_and_reports():
    errors: list[str] = []

    def broken(pin, active_high):
        raise RuntimeError("no gpio")

    led = make_status_led(17, device_factory=broken, on_error=errors.append)
    led.set(LedState.ERROR)

    assert led.enabled is False
    assert errors == ["no gpio"]


def test_led_runtime_failure_never_raises():
    led = StatusLed(_FakeLed(fail=True))

    led.set(LedState.WARNING)
    led.set(LedState.ACTIVE)

    assert led.enabled is False


def test_led_close_turns_off_and_releases():
    device = _FakeLed()
    led = StatusLed(device)
    led.set(LedState.ACTIVE)

    led.close()

    assert device.calls[-2:] == [("off",), ("close",)]
    assert led.enabled is False
    assert led.state is LedState.OFF


def test_led_state_for_runtime_state():
    assert led_state_for(RuntimeState(network_online=True)) is LedState.ACTIVE
    assert led_state_for(RuntimeState()) is LedState.ACTIVE
    assert led_state_for(RuntimeState(network_online=False)) is LedState.WARNING
    assert led_state_for(RuntimeState(thermal_saver_active=True)) is LedState.WARNING
    assert led_state_for(RuntimeState(disk_low_alert_sent=True)) is LedState.WARNING
    assert (
        led_state_for(RuntimeState(network_online=False, battery_critical_active=True))
        is LedState.ERROR
    )
    assert led_state_for(RuntimeState(thermal_critical_alert_sent=True)) is LedState.ERROR


class _FakeLed:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple] = []

    def blink(self, on_time: float, off_time: float) -> None:
        if self.fail:
            raise RuntimeError("gpio lost")
        self.calls.append(("blink", on_time, off_time))

    def off(self) -> None:
        self.calls.append(("off",))

    def close(self) -> None:
        self.calls.append(("close",))
