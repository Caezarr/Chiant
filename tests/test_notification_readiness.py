from __future__ import annotations

import hashlib
import json

from boring.notification_readiness import run_notification_test, write_report


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_notification_test_passes_on_2xx(tmp_path):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return FakeResponse(204)

    report = run_notification_test(
        webhook_url="https://notify.example.test/boring",
        post=fake_post,
    )

    assert report.passed is True
    assert report.webhook_host == "notify.example.test"
    assert report.webhook_hash == _hash("https://notify.example.test/boring")
    assert report.sound is True
    assert calls[0][1]["title"] == "Boring Box - test notification"
    assert calls[0][1]["sound"] is True

    output = tmp_path / "reports" / "notification-test.json"
    write_report(report, output)
    payload = json.loads(output.read_text())
    assert payload["passed"] is True
    assert payload["sound"] is True
    assert payload["webhook_hash"] == _hash("https://notify.example.test/boring")


def test_notification_test_fails_without_webhook():
    report = run_notification_test(webhook_url=None)

    assert report.passed is False
    assert report.webhook_hash == ""
    assert report.sound is True
    assert report.error == "missing webhook url"


def test_notification_test_fails_on_non_2xx():
    report = run_notification_test(
        webhook_url="https://notify.example.test/boring",
        post=lambda *_, **__: FakeResponse(500),
    )

    assert report.passed is False
    assert report.status_code == 500
    assert report.error == "HTTP 500"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
