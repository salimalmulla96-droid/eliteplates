import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

HISTORY_PATH = DATA_DIR / "search_history.json"
FAVORITES_PATH = DATA_DIR / "favorites.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

ALERTS_PATH = DATA_DIR / "alerts.json"
ALERT_LOGS_PATH = DATA_DIR / "alert_logs.json"
INSTAGRAM_SETTINGS_PATH = DATA_DIR / "instagram_settings.json"
INSTAGRAM_SEEN_POSTS_PATH = DATA_DIR / "instagram_seen_posts.json"


DEFAULT_SETTINGS = {
    "theme": "dark",
    "accent": "purple",
    "default_search_depth": "All pages",
    "table_density": "comfortable",
    "save_history": True,
    "show_seller_details": True,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "telegram_message_title": "New Plate Alert",
    "telegram_compact_mode": False,
    "telegram_emojis": True,
    "telegram_include_seller_details": True,
    "telegram_include_detected_time": True,
    "telegram_include_match_reason": True,
    "enrich_listing_details": False,
    "include_sold_listings": False,
    "max_listings_per_scan": 1000,
    "max_pages_per_scan": 20,
    "fresh_listing_window_minutes": 15,
}

DEFAULT_INSTAGRAM_SETTINGS = {
    "enabled": False,
    "instagram_provider": "Apify",
    "apify_api_token": "",
    "apify_actor_id": "apify/instagram-post-scraper",
    "provider_connected": False,
    "last_provider_error": "",
    "accounts": [
        {"username": "rak.number", "enabled": True, "last_checked_at": "", "last_detected_post": "", "seen_count": 0},
        {"username": "PLATESELITE", "enabled": True, "last_checked_at": "", "last_detected_post": "", "seen_count": 0},
    ],
    "check_interval_minutes": 10,
    "send_all_new_posts": True,
    "extract_plate_numbers": False,
    "send_instagram_image_to_telegram": True,
    "extract_plate_details_from_images": False,
    "only_send_when_ocr_detects_plate_text": False,
    "include_caption": False,
    "include_post_image": True,
    "baseline_completed": False,
    "instagram_activated_at": "",
    "instagram_baseline_created_at": "",
    "seen_instagram_posts": {},
    "last_instagram_scan_at": "",
    "last_baseline_reset_at": "",
    "last_checked_at": "",
}

def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_history() -> list[dict[str, Any]]:
    return read_json(HISTORY_PATH, [])


def save_search(search: dict[str, Any], result_count: int) -> dict[str, Any]:
    history = get_history()
    key_fields = [
        "plate_number",
        "search_mode",
        "cities",
        "city",
        "code",
        "price_min",
        "price_max",
        "contains",
        "starts_with",
        "ends_with",
        "number_format",
        "search_depth",
        "sort",
        "hide_duplicates",
        "show_seller_details",
    ]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = None
    for item in history:
        if all(item.get(field, "") == search.get(field, "") for field in key_fields):
            existing = item
            break
    if existing:
        existing["datetime"] = now
        existing["searched_at"] = now
        existing["result_count"] = result_count
    else:
        existing = {"id": str(uuid.uuid4()), **search, "datetime": now, "searched_at": now, "result_count": result_count}
        history.insert(0, existing)
    write_json(HISTORY_PATH, history[:200])
    return existing


def delete_history_item(item_id: str) -> None:
    write_json(HISTORY_PATH, [item for item in get_history() if item.get("id") != item_id])


def clear_history() -> None:
    write_json(HISTORY_PATH, [])


def get_favorites() -> list[dict[str, Any]]:
    return read_json(FAVORITES_PATH, [])


def save_favorite(listing: dict[str, Any]) -> list[dict[str, Any]]:
    favorites = get_favorites()
    link = listing.get("listing_link") or listing.get("listing_url")
    if link and not any(item.get("listing_link") == link for item in favorites):
        favorites.insert(0, listing)
    write_json(FAVORITES_PATH, favorites)
    return favorites


def delete_favorite(item_id: str) -> None:
    favorites = [
        item
        for item in get_favorites()
        if item.get("listing_link") != item_id and item.get("id") != item_id
    ]
    write_json(FAVORITES_PATH, favorites)


def clear_favorites() -> None:
    write_json(FAVORITES_PATH, [])


def get_settings() -> dict[str, Any]:
    return {**DEFAULT_SETTINGS, **read_json(SETTINGS_PATH, {})}


def save_settings(settings: dict[str, Any]) -> dict[str, Any]:
    if settings.get("telegram_channel_id") and not settings.get("telegram_chat_id"):
        settings = {**settings, "telegram_chat_id": settings.get("telegram_channel_id")}
    merged = {**get_settings(), **settings}
    write_json(SETTINGS_PATH, merged)
    return merged


def get_instagram_settings() -> dict[str, Any]:
    return {**DEFAULT_INSTAGRAM_SETTINGS, **read_json(INSTAGRAM_SETTINGS_PATH, {})}


def save_instagram_settings(settings: dict[str, Any]) -> dict[str, Any]:
    settings = {
        key: value
        for key, value in settings.items()
        if key not in {"telegram_bot_token", "telegram_chat_id", "telegram_channel_id"}
    }
    merged = {**get_instagram_settings(), **settings}
    write_json(INSTAGRAM_SETTINGS_PATH, merged)
    return merged


def get_instagram_seen_posts() -> dict[str, Any]:
    return read_json(INSTAGRAM_SEEN_POSTS_PATH, {})


def save_instagram_seen_posts(seen_posts: dict[str, Any]) -> dict[str, Any]:
    write_json(INSTAGRAM_SEEN_POSTS_PATH, seen_posts)
    return seen_posts


def get_alerts() -> list[dict[str, Any]]:
    return read_json(ALERTS_PATH, [])


def write_alerts(alerts: list[dict[str, Any]]) -> None:
    write_json(ALERTS_PATH, alerts)


def save_alert(alert: dict[str, Any]) -> dict[str, Any]:
    alerts = get_alerts()
    existing = next((a for a in alerts if a.get('id') == alert.get('id')), None)
    if existing:
        alerts = [alert if a.get('id') == alert.get('id') else a for a in alerts]
    else:
        alerts.insert(0, alert)
    write_alerts(alerts)
    return alert


def delete_alert(alert_id: str) -> None:
    alerts = [a for a in get_alerts() if a.get('id') != alert_id]
    write_alerts(alerts)


def get_alert_logs() -> list[dict[str, Any]]:
    return read_json(ALERT_LOGS_PATH, [])


def write_alert_logs(logs: list[dict[str, Any]]) -> None:
    write_json(ALERT_LOGS_PATH, logs)


def add_alert_log(log: dict[str, Any]) -> dict[str, Any]:
    logs = get_alert_logs()
    logs.insert(0, log)
    write_alert_logs(logs)
    return log


def clear_alert_logs() -> None:
    write_alert_logs([])
