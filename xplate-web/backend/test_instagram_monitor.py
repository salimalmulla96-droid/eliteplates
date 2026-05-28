from app import instagram_monitor


def test_latest_post_skips_pinned_and_uses_newest_timestamp(monkeypatch):
    items = [
        {
            "url": "https://www.instagram.com/p/PINNED/",
            "shortCode": "PINNED",
            "timestamp": "2026-05-26T10:00:00Z",
            "isPinned": True,
            "displayUrl": "https://image/pinned.jpg",
        },
        {
            "url": "https://www.instagram.com/p/OLDER/",
            "shortCode": "OLDER",
            "timestamp": "2026-05-26T08:00:00Z",
            "displayUrl": "https://image/older.jpg",
        },
        {
            "url": "https://www.instagram.com/p/NEWEST/",
            "shortCode": "NEWEST",
            "taken_at": "2026-05-26T09:00:00Z",
            "displayUrl": "https://image/newest.jpg",
        },
    ]

    class Response:
        status_code = 200

        def json(self):
            return items

    monkeypatch.setattr(instagram_monitor.requests, "post", lambda *args, **kwargs: Response())
    details = []
    post, returned = instagram_monitor.fetch_latest_post(
        "raknumber",
        {"instagram_provider": "Apify", "apify_api_token": "token", "apify_actor_id": "apify/instagram-scraper"},
        details,
    )

    assert returned == 3
    assert post["shortcode"] == "NEWEST"
    assert any("pinned posts skipped: 1" in line for line in details)
    assert any("selected latest post: NEWEST" in line for line in details)


def test_instagram_caption_uses_post_link_not_profile_link():
    caption = instagram_monitor._instagram_caption(
        {
            "username": "raknumber",
            "account": "raknumber",
            "shortcode": "SHORT123",
            "post_url": "",
            "caption": "Plate caption",
            "ocr_text": "12345 Dubai A",
            "seller_name": "?",
            "phone_number": "?",
        },
        {"include_caption": True, "extract_plate_details_from_images": True},
    )

    assert "New Instagram Post" in caption
    assert "Account: raknumber" in caption
    assert "Username: raknumber" in caption
    assert "Seller: ?" in caption
    assert "Phone: ?" in caption
    assert "Caption:" in caption
    assert "Plate caption" in caption
    assert "OCR enabled: yes" in caption
    assert "OCR detected text:" in caption
    assert "12345 Dubai A" in caption
    assert "Post:" in caption
    assert "https://www.instagram.com/p/SHORT123/" in caption
    assert "https://www.instagram.com/raknumber/" not in caption


def test_instagram_caption_hides_ocr_when_disabled():
    caption = instagram_monitor._instagram_caption(
        {"username": "raknumber", "shortcode": "SHORT123", "ocr_text": "12345"},
        {"extract_plate_details_from_images": False},
    )

    assert "OCR detected text:" not in caption


def test_instagram_phone_and_seller_extraction_from_provider_data():
    post = instagram_monitor._normalize_apify_post(
        {
            "shortCode": "SHORT123",
            "caption": "WhatsApp 050 123 4567",
            "ownerFullName": "RAK Number",
            "displayUrl": "https://image/full.jpg",
            "thumbnailUrl": "https://image/thumb.jpg",
        },
        "raknumber",
    )

    assert post["seller_name"] == "RAK Number"
    assert post["phone_number"] == "0501234567"
    assert post["image_url"] == "https://image/full.jpg"
    assert post["image_url_type"] == "displayUrl"


def test_run_instagram_check_sends_new_posts_for_all_accounts(monkeypatch):
    settings = {
        "enabled": True,
        "instagram_provider": "Apify",
        "apify_api_token": "token",
        "apify_actor_id": "actor",
        "accounts": [{"username": "one"}, {"username": "two"}],
        "send_all_new_posts": True,
        "extract_plate_details_from_images": False,
        "include_post_image": True,
        "send_instagram_image_to_telegram": True,
        "baseline_completed": True,
        "instagram_activated_at": "2026-01-01 00:00:00",
    }
    saved_seen = {}
    sent = []

    monkeypatch.setattr(instagram_monitor, "get_instagram_settings", lambda: settings.copy())
    monkeypatch.setattr(instagram_monitor, "get_instagram_seen_posts", lambda: {})
    monkeypatch.setattr(instagram_monitor, "save_instagram_seen_posts", lambda seen: saved_seen.update(seen) or seen)
    monkeypatch.setattr(instagram_monitor, "save_instagram_settings", lambda next_settings: next_settings)
    monkeypatch.setattr(instagram_monitor, "_telegram_log_details", lambda: (["telegram ready"], True))
    monkeypatch.setattr(instagram_monitor, "_require_provider", lambda next_settings: ("Apify", "token", "actor"))
    monkeypatch.setattr(instagram_monitor, "_log", lambda *args, **kwargs: None)

    def fake_fetch(username, next_settings, details=None):
        return {
            "username": username,
            "post_url": f"https://www.instagram.com/p/{username.upper()}/",
            "shortcode": username.upper(),
            "image_url": f"https://image/{username}.jpg",
            "caption": "",
        }, 1

    monkeypatch.setattr(instagram_monitor, "fetch_latest_post", fake_fetch)
    monkeypatch.setattr(instagram_monitor, "_send_instagram_post", lambda post, next_settings, details: sent.append(post["username"]))

    result = instagram_monitor.run_instagram_check()

    assert result["sent"] == 2
    assert sent == ["one", "two"]
    assert saved_seen["one"] == ["shortcode:ONE"]
    assert saved_seen["two"] == ["shortcode:TWO"]
