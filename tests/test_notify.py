from __future__ import annotations

import httpx

from boring import notify as notify_module


class FakeResponse:
    def __init__(self, status_code: int = 204) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("fail", request=None, response=None)


def test_notify_returns_true_when_webhook_succeeds(monkeypatch):
    monkeypatch.setenv("BORING_NOTIFY_WEBHOOK_URL", "https://notify.example.test/boring")
    monkeypatch.setattr(notify_module.httpx, "post", lambda *_, **__: FakeResponse())

    assert notify_module.notify("title", "message") is True


def test_notify_returns_false_when_webhook_fails_on_headless_linux(monkeypatch):
    monkeypatch.setenv("BORING_NOTIFY_WEBHOOK_URL", "https://notify.example.test/boring")
    monkeypatch.setattr(notify_module.sys, "platform", "linux")
    monkeypatch.setattr(notify_module.httpx, "post", lambda *_, **__: FakeResponse(500))

    assert notify_module.notify("title", "message") is False
