from __future__ import annotations

from scripts.parse_paybyphone_har import extract_flow_summary


def test_extract_flow_summary_detects_critical_payment_flow():
    records = [
        {
            "method": "POST",
            "url": "https://api.paybyphone.test/auth/token",
            "request_body": "grant_type=password&client_id=client",
            "response_status": 200,
        },
        {
            "method": "GET",
            "url": "https://api.paybyphone.test/parking/accounts",
            "response_status": 200,
        },
        {
            "method": "GET",
            "url": "https://api.paybyphone.test/parking/locations?lat=50&lng=3",
            "response_status": 200,
        },
        {
            "method": "POST",
            "url": "https://api.paybyphone.test/parking/accounts/A1/sessions",
            "request_body": '{"rateOptionId":"rate","paymentMethodId":"pm"}',
            "response_status": 201,
        },
        {
            "method": "GET",
            "url": "https://api.paybyphone.test/parking/accounts/A1/sessions/current",
            "response_status": 200,
        },
        {
            "method": "DELETE",
            "url": "https://api.paybyphone.test/parking/accounts/A1/sessions/S1",
            "response_status": 204,
        },
    ]

    summary = extract_flow_summary(records)

    assert summary["auth"] is True
    assert summary["account_lookup"] is True
    assert summary["location_lookup"] is True
    assert summary["session_start"] is True
    assert summary["active_session_check"] is True
    assert summary["session_stop"] is True
    assert summary["successful_statuses"] == 6
    assert summary["failed_statuses"] == 0


def test_extract_flow_summary_keeps_missing_stop_false():
    summary = extract_flow_summary(
        [
            {
                "method": "POST",
                "url": "https://api.paybyphone.test/parking/accounts/A1/sessions",
                "response_status": 201,
            }
        ]
    )

    assert summary["session_start"] is True
    assert summary["session_stop"] is False
