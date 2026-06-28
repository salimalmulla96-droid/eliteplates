from fastapi.testclient import TestClient

from app import alerts
from app.main import app


def test_environment_telegram_configuration_is_supported(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345678:environment-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")
    monkeypatch.setattr(alerts, "get_settings", lambda: {
        "telegram_bot_token": "",
        "telegram_chat_id": "",
    })

    token, chat_id = alerts.load_telegram_configuration()

    assert token == "12345678:environment-token"
    assert chat_id == "-1001234567890"
    assert alerts.mask_token(token) == "12345678...oken"


def test_rule_credentials_take_precedence_over_environment_and_settings(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "environment-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@environment")
    monkeypatch.setattr(alerts, "get_settings", lambda: {
        "telegram_bot_token": "settings-token",
        "telegram_chat_id": "@settings",
    })

    token, chat_id = alerts.load_telegram_configuration({
        "telegram_bot_token": "rule-token",
        "telegram_chat_id": "@rule",
    })

    assert token == "rule-token"
    assert chat_id == "@rule"


def test_telegram_test_endpoint_uses_shared_sender(monkeypatch):
    monkeypatch.setattr(
        alerts,
        "load_telegram_configuration",
        lambda alert=None: ("test-token", "@eliteplates"),
    )
    monkeypatch.setattr(
        alerts,
        "send_telegram_message",
        lambda token, chat_id, text: {
            "ok": True,
            "result": {"message_id": 9001},
        },
    )

    response = TestClient(app).post("/telegram/test")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "message": "Telegram test message sent successfully",
        "telegram_message_id": 9001,
    }


def test_debug_send_bypasses_duplicate_history_only(monkeypatch):
    rule = {
        "id": "rule-1",
        "name": "Dubai VIP watch",
        "enabled": True,
        "cities": ["Dubai"],
        "city": "Dubai",
        "number_format": "Any format",
        "number_formats": [],
        "sent_listing_keys": ["id:123"],
        "seen_listing_keys": ["id:123"],
    }
    listing = {
        "listing_id": "123",
        "city": "Dubai",
        "code": "A",
        "plate_number": "89898",
        "price": "AED 40,000",
        "source": "Website",
        "listing_link": "https://example.test/license-plates/123",
        "featured": False,
        "sold": False,
    }
    send_calls = []
    monkeypatch.setattr(alerts, "_search_rows", lambda alert: [listing])
    monkeypatch.setattr(alerts, "_storage_alert", lambda alert_id: rule)
    monkeypatch.setattr(
        alerts,
        "_resolve_telegram_credentials",
        lambda alert: ("test-token", "@eliteplates"),
    )
    monkeypatch.setattr(alerts, "add_alert_log", lambda log: log)

    def fake_send(token, chat_id, alert, row, plate_info=None, bypass_duplicate_protection=False):
        send_calls.append({
            "token": token,
            "chat_id": chat_id,
            "plate": row["plate_number"],
            "bypass": bypass_duplicate_protection,
        })
        return {"sent": True, "skipped": False, "telegram_response": {"ok": True}}

    monkeypatch.setattr(alerts, "send_telegram_plate_alert", fake_send)

    result = alerts.debug_send_alert_matches(rule)

    assert result["raw_count"] == 1
    assert result["filtered_count"] == 1
    assert result["skipped_duplicates"] == 1
    assert result["sent_count"] == 1
    assert result["duplicate_history_bypassed"] is True
    assert send_calls == [{
        "token": "test-token",
        "chat_id": "@eliteplates",
        "plate": "89898",
        "bypass": True,
    }]
