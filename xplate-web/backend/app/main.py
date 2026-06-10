import os
import threading
import time
import uuid
import html
import re
import traceback
from datetime import datetime
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .exports import export_csv, export_excel
from .filters import apply_filters, seller_summary, summarize
from .models import (
    Alert,
    ExportRequest,
    FavoriteRequest,
    HistoryRunRequest,
    SearchRequest,
    SellerPlatesRequest,
    SettingsRequest,
)
from .scraper import (
    CITIES,
    NUMBER_FORMAT_CATALOG,
    NUMBER_FORMAT_OPTIONS,
    get_format_pattern,
    get_required_digit_length,
    get_seller_plates,
    normalize_number_formats,
    number_format_label,
    price_to_number,
    search_xplate,
    sort_results,
)
from .storage import (
    DATA_DIR,
    ALERTS_PATH,
    ALERT_LOGS_PATH,
    FAVORITES_PATH,
    HISTORY_PATH,
    INSTAGRAM_SEEN_POSTS_PATH,
    INSTAGRAM_SETTINGS_PATH,
    SETTINGS_PATH,
    clear_favorites,
    clear_history,
    delete_favorite,
    delete_history_item,
    get_favorites,
    get_history,
    get_settings,
    save_favorite,
    save_search,
    save_settings,
)
from .storage import get_alerts, save_alert, delete_alert, get_alert_logs, add_alert_log, clear_alert_logs, write_alerts
from . import alerts as alerts_module
from . import instagram_monitor
from . import plate_tracking
from .alert_config import get_config


app = FastAPI(title="Xplate Scout API")

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://eliteplates-six.vercel.app",
    "https://eliteplates-snowy.vercel.app",
]

frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    for origin in [item.strip() for item in frontend_url.split(",") if item.strip()]:
        if origin not in allowed_origins:
            allowed_origins.append(origin)

print("Allowed CORS origins:", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LATEST_RESULTS: list[dict[str, Any]] = []
LATEST_DEBUG: list[str] = []
JOBS: dict[str, dict[str, Any]] = {}


def _runtime_environment() -> str:
    explicit = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or os.getenv("RAILWAY_ENVIRONMENT") or "").strip().lower()
    if explicit in {"production", "prod"} or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        return "production"
    return "local"


def _telegram_configured() -> bool:
    settings_data = get_settings()
    return bool(
        str(settings_data.get('telegram_bot_token', '') or '').strip()
        and alerts_module.normalize_telegram_channel_id(settings_data.get('telegram_chat_id', '') or settings_data.get('telegram_channel_id', ''))
    )


def _log_production_startup() -> None:
    alerts = get_alerts()
    enabled_alerts = [alert for alert in alerts if _is_alert_enabled(alert)]
    print("backend started")
    print(f"environment: {_runtime_environment()}")
    print(f"DATA_DIR path: {DATA_DIR}")
    print(f"alerts storage path: {ALERTS_PATH}")
    print(f"settings storage path: {SETTINGS_PATH}")
    print(f"telegram settings path: {SETTINGS_PATH}")
    print(f"instagram settings path: {INSTAGRAM_SETTINGS_PATH}")
    print(f"instagram seen posts path: {INSTAGRAM_SEEN_POSTS_PATH}")
    print(f"alert logs path: {ALERT_LOGS_PATH}")
    print(f"search history path: {HISTORY_PATH}")
    print(f"favorites path: {FAVORITES_PATH}")
    print(f"alerts loaded count: {len(alerts)}")
    print(f"enabled alerts count: {len(enabled_alerts)}")
    print(f"Telegram configured: {'yes' if _telegram_configured() else 'no'}")
    print(f"scheduler started: {'yes' if alerts_module.scheduler_running() else 'no'}")
    print(f"current Railway PORT: {os.getenv('PORT') or '(not set)'}")
    print(f"frontend URL / allowed CORS origins: {', '.join(allowed_origins)}")

CITY_LABELS = {
    "dubai": "Dubai",
    "دبي": "Dubai",
    "abu dhabi": "Abu Dhabi",
    "abu-dhabi": "Abu Dhabi",
    "abudhabi": "Abu Dhabi",
    "أبوظبي": "Abu Dhabi",
    "ابوظبي": "Abu Dhabi",
    "sharjah": "Sharjah",
    "الشارقة": "Sharjah",
    "ajman": "Ajman",
    "عجمان": "Ajman",
    "ras al khaimah": "Ras Al Khaimah",
    "ras-al-khaimah": "Ras Al Khaimah",
    "rak": "Ras Al Khaimah",
    "r.a.k": "Ras Al Khaimah",
    "r a k": "Ras Al Khaimah",
    "رأس الخيمة": "Ras Al Khaimah",
    "راس الخيمة": "Ras Al Khaimah",
    "umm al quwain": "Umm Al Quwain",
    "umm-al-quwain": "Umm Al Quwain",
    "umm al qaiwain": "Umm Al Quwain",
    "أم القيوين": "Umm Al Quwain",
    "ام القيوين": "Umm Al Quwain",
    "fujairah": "Fujairah",
    "الفجيرة": "Fujairah",
}


def _normalize_city_label(city: Any) -> str:
    text = str(city or "").strip()
    if not text or text.lower() in {"all", "all cities"}:
        return ""
    key = text.lower().replace("_", " ")
    key_without_dots = re.sub(r"[.]", " ", key)
    key_without_dots = re.sub(r"\s+", " ", key_without_dots).strip()
    compact = re.sub(r"[\s.]", "", key)
    return CITY_LABELS.get(key) or CITY_LABELS.get(key.replace("-", " ")) or CITY_LABELS.get(key_without_dots) or CITY_LABELS.get(compact) or text.title()


def _normalize_alert_cities(alert: dict[str, Any]) -> list[str]:
    raw_cities = alert.get("cities") if isinstance(alert.get("cities"), list) else []
    if not raw_cities and alert.get("city"):
        raw_cities = [alert.get("city")]
    cities: list[str] = []
    for city in raw_cities:
        label = _normalize_city_label(city)
        if label and label not in cities:
            cities.append(label)
    alert["cities"] = cities
    alert["city"] = cities[0] if cities else ""
    return cities


def _is_alert_enabled(alert: dict[str, Any]) -> bool:
    value = alert.get("enabled")
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "enabled", "on"}
    return bool(value)


def _city_to_scraper_value(city: Any) -> str:
    label = _normalize_city_label(city)
    return label.lower() if label else ""


def _selected_cities(request: SearchRequest) -> list[str] | None:
    cities = [_city_to_scraper_value(city) for city in request.cities if str(city).strip()]
    if request.city and not cities:
        cities = [_city_to_scraper_value(request.city)]
    cities = [city for city in cities if city not in {"all", "all cities"}]
    return cities or None


def _normalize_alert_number_formats(alert: dict[str, Any]) -> list[str]:
    formats = normalize_number_formats(alert.get("number_formats"), fallback=alert.get("number_format"))
    alert["number_formats"] = formats
    alert["number_format"] = number_format_label(formats[0]) if formats else "Any format"
    return formats


def _run_search(request: SearchRequest, progress_callback=None) -> dict[str, Any]:
    global LATEST_RESULTS, LATEST_DEBUG
    debug: list[str] = []

    def collect_debug(message: str):
        debug.append(message)

    raw_results = search_xplate(
        number=request.plate_number,
        search_mode=request.search_mode,
        code=request.code,
        contains=request.contains,
        starts_with=request.starts_with,
        ends_with=request.ends_with,
        min_price=request.price_min,
        max_price=request.price_max,
        cities=_selected_cities(request),
        number_format=request.number_format,
        number_formats=request.number_formats,
        search_depth=request.search_depth,
        sort_mode=request.sort,
        debug_callback=collect_debug,
        progress_callback=progress_callback,
    )
    results = apply_filters(raw_results, request)
    LATEST_RESULTS = results
    LATEST_DEBUG = debug
    if get_settings().get("save_history", True):
        save_search(request.model_dump(), len(results))
    return {
        "results": results,
        "summary": summarize(results),
        "debug": {
            "lines": debug,
            "selected_format": request.number_format,
            "selected_formats": [number_format_label(item) for item in normalize_number_formats(request.number_formats, fallback=request.number_format)],
            "url_format_value": get_format_pattern(request.number_format),
            "required_digit_length": get_required_digit_length(request.number_format),
            "final_count": len(results),
        },
    }


def _city_match(row: dict[str, Any], city: str) -> bool:
    return str(row.get("city", "")).strip().lower() == str(city).strip().lower()


def _seller_key_match(row: dict[str, Any], request: SellerPlatesRequest) -> bool:
    username = (request.seller_username or "").strip()
    profile = (request.seller_profile_url or request.seller_link or "").strip()
    phone = (request.phone_number or "").strip()
    name = (request.seller_name or "").strip()
    if username and username != "?":
        return row.get("seller_username") == username
    if profile:
        return row.get("seller_link") == profile or row.get("seller_profile_url") == profile
    if phone and phone != "?":
        return row.get("phone_number") == phone
    if name and name != "Unknown":
        return row.get("seller_name") == name
    return False


def _seller_response(rows: list[dict[str, Any]], seed: SellerPlatesRequest) -> dict[str, Any]:
    rows = sort_results(rows, "Newest first")
    prices = [price_to_number(row.get("price", "")) for row in rows]
    prices = [price for price in prices if price is not None]
    seller = {
        "seller_name": seed.seller_name or (rows[0].get("seller_name") if rows else "Unknown"),
        "seller_username": seed.seller_username or (rows[0].get("seller_username") if rows else "?"),
        "phone_number": seed.phone_number or (rows[0].get("phone_number") if rows else "?"),
        "seller_profile_url": seed.seller_profile_url or seed.seller_link or (rows[0].get("seller_link") if rows else ""),
        "total_listings": len(rows),
        "cheapest": min(prices) if prices else None,
        "most_expensive": max(prices) if prices else None,
        "cities": sorted({row.get("city", "") for row in rows if row.get("city")}),
        "newest_listing": max((f"{row.get('uploaded_date', '')} {row.get('uploaded_time', '')}".strip() for row in rows), default=""),
    }
    return {"seller": seller, "results": rows}


@app.get("/")
def root_health():
    return {"status": "ok", "app": "Xplate Scout"}


@app.get("/api/health")
def api_health():
    return {"status": "ok", "app": "Xplate Scout"}


@app.get("/api/options")
def options():
    return {
        "cities": CITIES,
        "number_formats": NUMBER_FORMAT_OPTIONS,
        "number_format_catalog": NUMBER_FORMAT_CATALOG,
        "codes": ['Any code', '?', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'R', 'S', 'T', 'X', 'Y', 'Z', 'AA', 'BB', 'CC'],
        "search_modes": ['exact match', 'contains', 'starts with', 'ends with'],
        "intervals": [20, 30, 60, 300],
        "search_depths": ["First page only", "First 5 pages", "First 10 pages", "All pages"],
        "sorts": ["Newest first", "Oldest first", "Cheapest first", "Most expensive first", "Seller name A-Z", "City A-Z", "Code A-Z"],
    }


@app.post("/api/search")
def search(request: SearchRequest):
    return _run_search(request)


@app.post("/api/search/start")
def search_start(request: SearchRequest):
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "running",
        "created_at": time.time(),
        "request": request.model_dump(),
        "current_city": "",
        "current_page": 0,
        "pages_done": 0,
        "pages_total": None,
        "results_so_far": 0,
        "progress_percent": None,
        "estimated_seconds_remaining": None,
        "message": "Starting search...",
        "result": None,
        "error": "",
    }

    def progress(update: dict[str, Any]):
        current = JOBS.get(job_id)
        if not current:
            return
        current.update(update)
        if current.get("progress_percent") is None:
            current["message"] = update.get("message", current["message"])

    def worker():
        try:
            result = _run_search(request, progress_callback=progress)
            JOBS[job_id].update({
                "status": "done",
                "result": result,
                "results_so_far": len(result["results"]),
                "progress_percent": 100,
                "estimated_seconds_remaining": 0,
                "message": f"Done. Found {len(result['results'])} results.",
                "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception as exc:
            JOBS[job_id].update({
                "status": "error",
                "error": str(exc),
                "message": "Search failed. Please adjust filters or try again.",
                "progress_percent": 100,
            })

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/search/progress/{job_id}")
def search_progress(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Search job not found")
    return {key: value for key, value in job.items() if key not in {"request", "result"}}


@app.get("/api/search/result/{job_id}")
def search_result(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Search job not found")
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error") or "Search failed")
    if job["status"] != "done":
        return {"status": job["status"], "results": [], "summary": {}, "debug": {}}
    return {"status": "done", **job["result"]}


@app.post("/api/seller/plates")
def seller_plates(request: SellerPlatesRequest):
    profile_url = request.seller_profile_url or request.seller_link
    profile_rows: list[dict[str, Any]] = []
    if profile_url:
        try:
            profile_rows = get_seller_plates(profile_url, max_pages=3, timeout=10)
        except Exception:
            profile_rows = []

    current_rows = request.current_results or LATEST_RESULTS
    matched_rows = [row for row in current_rows if _seller_key_match(row, request)]
    seen = set()
    merged: list[dict[str, Any]] = []
    for row in [*profile_rows, *matched_rows]:
        row.setdefault("seller_name", request.seller_name or "Unknown")
        row.setdefault("seller_username", request.seller_username or "?")
        row.setdefault("phone_number", request.phone_number or "?")
        row.setdefault("seller_link", request.seller_profile_url or request.seller_link or "")
        row.setdefault("deal_rank", "Normal")
        link = row.get("listing_link") or row.get("listing_url") or f"{row.get('plate_number')}-{row.get('code')}-{row.get('city')}"
        if link in seen:
            continue
        seen.add(link)
        merged.append(row)
    return _seller_response(merged, request)


@app.get("/api/history")
def history():
    return {"history": get_history()}


@app.post("/api/history/run")
def history_run(request: HistoryRunRequest):
    item = next((entry for entry in get_history() if entry.get("id") == request.id), None)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    return search(SearchRequest(**item))


@app.delete("/api/history/{item_id}")
def history_delete(item_id: str):
    delete_history_item(item_id)
    return {"ok": True}


@app.delete("/api/history")
def history_clear():
    clear_history()
    return {"ok": True}


@app.get("/api/favorites")
def favorites():
    return {"favorites": get_favorites()}


@app.post("/api/favorites")
def favorite_add(request: FavoriteRequest):
    return {"favorites": save_favorite(request.listing)}


@app.delete("/api/favorites/{item_id:path}")
def favorite_delete(item_id: str):
    delete_favorite(item_id)
    return {"favorites": get_favorites()}


@app.delete("/api/favorites")
def favorite_clear():
    clear_favorites()
    return {"favorites": []}


@app.get("/api/sellers")
def sellers():
    return {"sellers": seller_summary(LATEST_RESULTS)}


@app.post("/api/export/csv")
def export_to_csv(request: ExportRequest):
    return {"path": export_csv(request.rows or LATEST_RESULTS, request.filename_prefix)}


@app.post("/api/export/excel")
def export_to_excel(request: ExportRequest):
    return {"path": export_excel(request.rows or LATEST_RESULTS, request.filename_prefix)}


@app.get("/api/settings")
def settings():
    return {"settings": get_settings()}


@app.post("/api/settings")
def settings_save(request: SettingsRequest):
    return {"settings": save_settings(request.settings)}


@app.post("/api/telegram/verify")
def telegram_verify(payload: dict):
    bot_token = str(payload.get("telegram_bot_token") or get_settings().get("telegram_bot_token", "") or "").strip()
    chat_id = alerts_module.normalize_telegram_channel_id(payload.get("telegram_chat_id") or get_settings().get("telegram_chat_id", ""))
    result = {
        "ok": False,
        "token_valid": False,
        "channel_found": False,
        "bot_admin": False,
        "can_send": False,
        "normalized_channel_id": chat_id,
        "bot_username": "",
        "chat_title": "",
        "message": "",
        "raw_error": "",
    }
    if not bot_token:
        result["message"] = "Telegram bot token missing"
        return result
    if not chat_id:
        result["message"] = "Telegram channel ID missing"
        return result

    try:
        get_me = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        get_me_data = get_me.json()
        if not get_me.ok or not get_me_data.get("ok"):
            description = get_me_data.get("description") or get_me.text
            result["message"] = alerts_module.user_friendly_telegram_error(description)
            result["raw_error"] = description
            return result
        result["token_valid"] = True
        bot = get_me_data.get("result", {})
        bot_id = bot.get("id")
        result["bot_username"] = bot.get("username", "")

        get_chat = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getChat",
            params={"chat_id": chat_id},
            timeout=10,
        )
        get_chat_data = get_chat.json()
        if not get_chat.ok or not get_chat_data.get("ok"):
            description = get_chat_data.get("description") or get_chat.text
            result["message"] = "Channel not found. Check the Channel ID and make sure the bot is added as admin." if "chat not found" in description.lower() else alerts_module.user_friendly_telegram_error(description)
            result["raw_error"] = description
            return result
        result["channel_found"] = True
        chat = get_chat_data.get("result", {})
        result["chat_title"] = chat.get("title") or chat.get("username") or ""

        member = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getChatMember",
            params={"chat_id": chat_id, "user_id": bot_id},
            timeout=10,
        )
        member_data = member.json()
        if member.ok and member_data.get("ok"):
            member_result = member_data.get("result", {})
            status = member_result.get("status", "")
            can_post = bool(member_result.get("can_post_messages", False))
            result["bot_admin"] = status in {"administrator", "creator"}
            result["can_send"] = status == "creator" or can_post or status == "administrator"
            if result["can_send"]:
                result["ok"] = True
                result["message"] = "Telegram connection verified. Bot can post to this channel."
            else:
                result["message"] = "Bot can access the channel but is not allowed to post. Make the bot an admin with posting permission."
        else:
            description = member_data.get("description") if isinstance(member_data, dict) else member.text
            result["raw_error"] = description or ""
            result["message"] = "Channel found, but bot admin status could not be verified. Make sure the bot is added as an admin."
        return result
    except Exception as exc:
        result["message"] = alerts_module.user_friendly_telegram_error(str(exc))
        result["raw_error"] = str(exc)
        return result


@app.post("/api/telegram/test-channel")
def telegram_test_channel(payload: dict | None = None):
    payload = payload or {}
    settings = get_settings()
    bot_token = str(payload.get("telegram_bot_token") or settings.get("telegram_bot_token", "") or "").strip()
    chat_id = alerts_module.normalize_telegram_channel_id(payload.get("telegram_chat_id") or settings.get("telegram_chat_id", "") or settings.get("telegram_channel_id", ""))
    if not bot_token:
        return JSONResponse(status_code=400, content={"ok": False, "message": "Telegram bot token missing"})
    if not chat_id:
        return JSONResponse(status_code=400, content={"ok": False, "message": "Telegram channel ID missing"})
    try:
        sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"<b>Xplate Telegram test</b>\nChannel test sent at {html.escape(sent_at, quote=False)}."
        response = alerts_module.send_telegram_message(bot_token, chat_id, message)
        return {
            "ok": True,
            "message": "Test message sent to Telegram channel.",
            "normalized_channel_id": chat_id,
            "telegram_response": response,
        }
    except Exception as exc:
        error_message = alerts_module.user_friendly_telegram_error(str(exc))
        return JSONResponse(status_code=400, content={"ok": False, "message": error_message, "raw_error": str(exc)})


@app.get("/api/debug")
def debug():
    return {"lines": LATEST_DEBUG}


def _hydrate_alert_delivery_status(alert: dict[str, Any], logs: list[dict[str, Any]]) -> dict[str, Any]:
    alert_id = alert.get('id', '')
    today = datetime.now().strftime('%Y-%m-%d')
    sent_today = 0
    last_sent_at = ''
    for log in logs:
        if log.get('alert_id') != alert_id:
            continue
        sent_count = int(log.get('sent_notifications') or 0)
        checked_at = str(log.get('checked_at') or '')
        if sent_count > 0:
            if checked_at.startswith(today):
                sent_today += sent_count
            if not last_sent_at:
                last_sent_at = checked_at
    alert['sent_today'] = sent_today
    alert['last_sent_at'] = last_sent_at or alert.get('last_sent_at', '')
    return alert


@app.get('/api/alerts')
def api_get_alerts():
    migrated = []
    changed = False
    logs = get_alert_logs()
    for alert in get_alerts():
        if 'immediate_alerts_mode' not in alert:
            alert['immediate_alerts_mode'] = True
            alert['monitoring_interval_seconds'] = 20
            alert['check_interval_seconds'] = 20
            changed = True
        if 'sent_listing_keys' not in alert:
            alert['sent_listing_keys'] = []
            changed = True
        if not alert.get('max_pages_per_scan'):
            alert['max_pages_per_scan'] = alerts_module.AUTO_MAX_PAGES_PER_SCAN
            changed = True
        if not alert.get('max_listings_per_scan'):
            alert['max_listings_per_scan'] = alerts_module.AUTO_MAX_LISTINGS_PER_SCAN
            changed = True
        if not alert.get('fresh_listing_window_minutes'):
            alert['fresh_listing_window_minutes'] = alerts_module.AUTO_FRESH_LISTING_WINDOW_MINUTES
            changed = True
        previous_cities = list(alert.get('cities') or [])
        previous_city = alert.get('city', '')
        previous_formats = list(alert.get('number_formats') or [])
        previous_format = alert.get('number_format', '')
        _normalize_alert_cities(alert)
        _normalize_alert_number_formats(alert)
        if alert.get('cities') != previous_cities or alert.get('city', '') != previous_city:
            changed = True
        if alert.get('number_formats') != previous_formats or alert.get('number_format', '') != previous_format:
            changed = True
        alert['include_featured_listings'] = bool(alert.get('include_featured_listings', False))
        alert['include_sold_listings'] = bool(alert.get('include_sold_listings', False))
        if alert.get('baseline_created') and alert.get('baseline_completed') and not alert.get('max_seen_listing_id'):
            alert_model = Alert(**alert)
            alert['max_seen_listing_id'] = alerts_module._derive_max_seen_listing_id(alert_model)
            changed = True
        migrated.append(_hydrate_alert_delivery_status(alert, logs))
    if changed:
        write_alerts(migrated)
    enabled_alerts = [alert for alert in migrated if _is_alert_enabled(alert)]
    return {
        'alerts': migrated,
        'enabled_count': len(enabled_alerts),
        'enabled_alerts': [
            {
                'id': alert.get('id', ''),
                'name': alert.get('name', '') or alert.get('id', ''),
                'city': alert.get('city') or ', '.join(alert.get('cities') or []) or 'All cities',
                'enabled': _is_alert_enabled(alert),
            }
            for alert in enabled_alerts
        ],
    }


@app.post('/api/alerts')
def api_create_alert(alert: dict):
    # initialize fields
    _normalize_alert_cities(alert)
    _normalize_alert_number_formats(alert)
    print("Create alert city:", alert.get('city', ''))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    alert['id'] = alert.get('id') or str(uuid.uuid4())
    alert['created_at'] = now
    alert['updated_at'] = now
    alert['last_checked_at'] = ''
    alert['last_scan_at'] = ''
    alert['last_status'] = ''
    alert['last_match_count'] = 0
    if alert.get('send_all_new_plates') or str(alert.get('search_mode', '')).strip().lower() == 'send all new plates' or str(alert.get('name', '')).strip().upper() == 'ALL PLATES':
        alert['send_all_new_plates'] = True
        _normalize_alert_cities(alert)
    alert['immediate_alerts_mode'] = bool(alert.get('immediate_alerts_mode', True))
    default_interval = 20 if alert['immediate_alerts_mode'] else 60
    alert['max_pages_per_scan'] = int(alert.get('max_pages_per_scan') or alerts_module.AUTO_MAX_PAGES_PER_SCAN)
    alert['max_listings_per_scan'] = int(alert.get('max_listings_per_scan') or alerts_module.AUTO_MAX_LISTINGS_PER_SCAN)
    alert['include_featured_listings'] = bool(alert.get('include_featured_listings', False))
    alert['include_sold_listings'] = bool(alert.get('include_sold_listings', False))
    alert['enrich_listing_details'] = bool(alert.get('enrich_listing_details', False))
    alert['fresh_listing_window_minutes'] = int(alert.get('fresh_listing_window_minutes') or alerts_module.AUTO_FRESH_LISTING_WINDOW_MINUTES)
    alert['monitoring_interval_seconds'] = int(alert.get('monitoring_interval_seconds') or alert.get('check_interval_seconds') or default_interval)
    alert['check_interval_seconds'] = alert['monitoring_interval_seconds']
    alert['notified_listing_keys'] = alert.get('notified_listing_keys', [])
    alert['seen_listing_keys'] = alert.get('seen_listing_keys', [])
    alert['seen_listing_ids'] = alert.get('seen_listing_ids', [])
    alert['seen_listing_urls'] = alert.get('seen_listing_urls', [])
    alert['sent_listing_keys'] = alert.get('sent_listing_keys', [])
    alert['max_seen_listing_id'] = int(alert.get('max_seen_listing_id') or 0)
    alert['activated_at'] = alert.get('activated_at', '')
    alert['baseline_created_at'] = alert.get('baseline_created_at', '')
    alert['baseline_created'] = False
    alert['last_sent_at'] = alert.get('last_sent_at', '')
    alert['sent_today'] = int(alert.get('sent_today') or 0)
    save_alert(alert)
    baseline = alerts_module.initialize_baseline(alert)
    if _is_alert_enabled(baseline):
        alerts_module.clear_stop_all()
    alerts_module.clear_scheduler_cache()
    saved_alerts = get_alerts()
    print(f"Create alert saved alert id: {baseline.get('id') or alert.get('id') or '(missing)'}")
    print(f"Create alert saved alert name: {baseline.get('name') or alert.get('name') or '(unnamed)'}")
    print(f"Create alert saved city/cities: {baseline.get('cities') or baseline.get('city') or alert.get('cities') or alert.get('city') or 'All cities'}")
    print(f"Create alert storage path: {ALERTS_PATH}")
    print(f"Create alert total alerts count after saving: {len(saved_alerts)}")
    return {'alert': baseline, 'alerts': saved_alerts, 'message': 'Alert created. Future matching plates will be sent automatically.'}


@app.put('/api/alerts/{alert_id}')
def api_update_alert(alert_id: str, alert: dict):
    alerts = get_alerts()
    found = False
    for i, a in enumerate(alerts):
        if a.get('id') == alert_id:
            merged_alert = {**a, **alert}
            merged_alert['id'] = alert_id
            merged_alert['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            merged_alert['immediate_alerts_mode'] = bool(merged_alert.get('immediate_alerts_mode', True))
            default_interval = 20 if merged_alert['immediate_alerts_mode'] else 60
            merged_alert['monitoring_interval_seconds'] = int(merged_alert.get('monitoring_interval_seconds') or merged_alert.get('check_interval_seconds') or default_interval)
            merged_alert['check_interval_seconds'] = merged_alert['monitoring_interval_seconds']
            _normalize_alert_cities(merged_alert)
            _normalize_alert_number_formats(merged_alert)
            if merged_alert.get('send_all_new_plates') or str(merged_alert.get('search_mode', '')).strip().lower() == 'send all new plates' or str(merged_alert.get('name', '')).strip().upper() == 'ALL PLATES':
                merged_alert['send_all_new_plates'] = True
                _normalize_alert_cities(merged_alert)
            merged_alert['max_pages_per_scan'] = int(merged_alert.get('max_pages_per_scan') or alerts_module.AUTO_MAX_PAGES_PER_SCAN)
            merged_alert['max_listings_per_scan'] = int(merged_alert.get('max_listings_per_scan') or alerts_module.AUTO_MAX_LISTINGS_PER_SCAN)
            merged_alert['include_featured_listings'] = bool(merged_alert.get('include_featured_listings', False))
            merged_alert['include_sold_listings'] = bool(merged_alert.get('include_sold_listings', False))
            merged_alert['enrich_listing_details'] = bool(merged_alert.get('enrich_listing_details', False))
            merged_alert['fresh_listing_window_minutes'] = int(merged_alert.get('fresh_listing_window_minutes') or alerts_module.AUTO_FRESH_LISTING_WINDOW_MINUTES)
            merged_alert['sent_listing_keys'] = merged_alert.get('sent_listing_keys', [])
            alerts[i] = merged_alert
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail='Alert not found')
    write_alerts(alerts)
    if _is_alert_enabled(merged_alert):
        alerts_module.clear_stop_all()
    alerts_module.clear_scheduler_cache()
    return {'alert': merged_alert}


@app.delete('/api/alerts/clear-all')
def api_clear_all_alerts():
    alerts = get_alerts()
    removed_ids = [str(alert.get('id') or '') for alert in alerts if alert.get('id')]
    write_alerts([])
    alerts_module.request_stop_all(len(alerts))
    message = f"Cleared {len(alerts)} alert rule(s) from storage and cleared scheduler cache."
    add_alert_log({
        'id': str(uuid.uuid4()),
        'alert_id': 'clear-all',
        'alert_name': 'Clear all alerts',
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'all_cleared',
        'event_type': 'Skipped',
        'severity': 'warning',
        'message': message,
        'matches_count': 0,
        'sent_notifications': 0,
        'error': '',
        'listing': {},
        'reason': 'DELETE /api/alerts/clear-all called.',
        'details': [
            f"Removed alert IDs: {', '.join(removed_ids) if removed_ids else '(none)'}",
            'Alerts storage is now empty.',
            'Scheduler cache cleared.',
            'No Telegram messages will be sent until a new alert is created.',
        ],
    })
    return {
        'ok': True,
        'alerts': [],
        'removed_alert_ids': removed_ids,
        'enabled_count': 0,
        'message': message,
    }


@app.delete('/api/alerts/{alert_id}')
def api_delete_alert(alert_id: str):
    delete_alert(alert_id)
    alerts_module.clear_scheduler_cache()
    return {'ok': True}


@app.post('/api/alerts/{alert_id}/toggle')
def api_toggle_alert(alert_id: str):
    alerts = get_alerts()
    for a in alerts:
        if a.get('id') == alert_id:
            enabling = not _is_alert_enabled(a)
            alerts_module.clear_scheduler_cache()
            a['enabled'] = enabling
            a['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if enabling:
                alerts_module.clear_stop_all()
                a['baseline_completed'] = False
                a['baseline_created'] = False
                a['seen_listing_keys'] = []
                a['seen_listing_ids'] = []
                a['seen_listing_urls'] = []
                a['notified_listing_keys'] = []
                a['max_seen_listing_id'] = 0
            save_alert(a)
            if enabling:
                a = alerts_module.initialize_baseline(a)
                return {'alert': a, 'message': 'Baseline created. Future listings only.'}
            return {'alert': a}
    raise HTTPException(status_code=404, detail='Alert not found')


@app.post('/api/alerts/stop-all')
def api_stop_all_alerts():
    alerts = get_alerts()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    disabled_ids: list[str] = []
    for alert in alerts:
        if _is_alert_enabled(alert):
            disabled_ids.append(str(alert.get('id') or ''))
        alert['enabled'] = False
        alert['updated_at'] = now
    write_alerts(alerts)
    alerts_module.request_stop_all(len(disabled_ids))
    stop_message = f"STOP ALL ALERTS: disabled {len(disabled_ids)} alerts and cleared scheduler cache"
    add_alert_log({
        'id': str(uuid.uuid4()),
        'alert_id': 'stop-all',
        'alert_name': 'Emergency stop all',
        'checked_at': now,
        'status': 'all_disabled',
        'event_type': 'Skipped',
        'severity': 'warning',
        'message': stop_message,
        'matches_count': 0,
        'sent_notifications': 0,
        'error': '',
        'listing': {},
        'reason': 'Emergency stop-all endpoint called.',
        'details': [
            f"Disabled alert IDs: {', '.join(disabled_ids) if disabled_ids else '(none)'}",
            'Scheduler cache cleared.',
            'Future Telegram sends are stopped until alerts are re-enabled.',
        ],
    })
    return {
        'ok': True,
        'alerts': alerts,
        'disabled_alert_ids': disabled_ids,
        'enabled_count': 0,
        'message': stop_message,
    }


@app.post('/api/alerts/{alert_id}/disable-others')
def api_disable_other_alerts(alert_id: str):
    alerts = get_alerts()
    selected = next((a for a in alerts if a.get('id') == alert_id), None)
    if not selected:
        raise HTTPException(status_code=404, detail='Alert not found')

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    disabled_ids: list[str] = []
    for alert in alerts:
        if alert.get('id') == alert_id:
            continue
        if _is_alert_enabled(alert):
            alert['enabled'] = False
            alert['updated_at'] = now
            disabled_ids.append(str(alert.get('id') or ''))
            alerts_module.RUNNING_ALERTS.pop(str(alert.get('id') or ''), None)

    write_alerts(alerts)
    alerts_module.clear_scheduler_cache()
    enabled_alerts = [alert for alert in alerts if _is_alert_enabled(alert)]
    add_alert_log({
        'id': str(uuid.uuid4()),
        'alert_id': alert_id,
        'alert_name': selected.get('name', ''),
        'checked_at': now,
        'status': 'safety_applied',
        'event_type': 'Skipped',
        'severity': 'warning',
        'message': f"Disabled {len(disabled_ids)} other alert rule(s). Only enabled rules now: {len(enabled_alerts)}.",
        'matches_count': 0,
        'sent_notifications': 0,
        'error': '',
        'listing': {},
        'reason': 'Disable all alerts except this one button clicked.',
        'details': [
            f"Alert ID: {alert_id}",
            f"Alert name: {selected.get('name', '') or alert_id}",
            f"Alert city: {selected.get('city') or ', '.join(selected.get('cities') or []) or 'All cities'}",
            f"Enabled: {'yes' if _is_alert_enabled(selected) else 'no'}",
            f"Disabled other alert IDs: {', '.join(disabled_ids) if disabled_ids else '(none)'}",
        ],
    })
    return {
        'ok': True,
        'alert': selected,
        'disabled_alert_ids': disabled_ids,
        'enabled_count': len(enabled_alerts),
        'message': f"Disabled {len(disabled_ids)} other alert rule(s).",
    }


@app.post('/api/alerts/{alert_id}/test-telegram')
def api_test_telegram(alert_id: str):
    checked_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"Test Telegram started for alert ID: {alert_id}")
    alert = None
    details = [
        'Button clicked: Test Telegram',
        f"Test Telegram started for alert ID: {alert_id}",
    ]
    try:
        alerts = get_alerts()
        alert = next((a for a in alerts if a.get('id') == alert_id), None)
        alert_found = bool(alert)
        print(f"Alert found: {'yes' if alert_found else 'no'}")
        details.append(f"Alert found: {'yes' if alert_found else 'no'}")
        if not alert:
            return JSONResponse(status_code=404, content={'ok': False, 'message': 'Alert not found', 'error': 'Alert not found'})

        settings_data = get_settings()
        bot_token = str(settings_data.get('telegram_bot_token', '') or '').strip()
        chat_id = alerts_module.normalize_telegram_channel_id(settings_data.get('telegram_chat_id', '') or settings_data.get('telegram_channel_id', ''))
        print(f"Telegram token loaded: {'yes' if bot_token else 'no'}")
        print(f"Telegram channel ID loaded: {'yes' if chat_id else 'no'}")
        details.extend([
            f"Rule loaded: {alert.get('name', '') or alert_id}",
            f"Telegram token loaded: {'yes' if bot_token else 'no'}",
            f"Telegram channel ID loaded: {'yes' if chat_id else 'no'}",
            f"Normalized channel ID: {chat_id or '(missing)'}",
        ])
        if not bot_token:
            message = 'Telegram bot token missing. Save Telegram settings first.'
            add_alert_log({
                'id': str(uuid.uuid4()),
                'alert_id': alert_id,
                'alert_name': alert.get('name', ''),
                'checked_at': checked_at,
                'status': 'test_error',
                'event_type': 'Error',
                'severity': 'error',
                'message': f'Test Telegram failed: {message}',
                'matches_count': 0,
                'sent_notifications': 0,
                'error': message,
                'listing': {},
                'reason': 'Telegram test failed.',
                'details': details,
            })
            return JSONResponse(status_code=400, content={'ok': False, 'message': message, 'error': message})
        if not chat_id:
            message = 'Telegram channel ID missing. Save Telegram settings first.'
            add_alert_log({
                'id': str(uuid.uuid4()),
                'alert_id': alert_id,
                'alert_name': alert.get('name', ''),
                'checked_at': checked_at,
                'status': 'test_error',
                'event_type': 'Error',
                'severity': 'error',
                'message': f'Test Telegram failed: {message}',
                'matches_count': 0,
                'sent_notifications': 0,
                'error': message,
                'listing': {},
                'reason': 'Telegram test failed.',
                'details': details,
            })
            return JSONResponse(status_code=400, content={'ok': False, 'message': message, 'error': message})

        rule_name = html.escape(str(alert.get('name') or 'Saved rule'), quote=False)
        msg = "\n".join([
            "🚨 <b>Telegram Test Alert</b>",
            "",
            "✅ This is a test message from Xplate Scout.",
            "",
            f"📡 <b>Rule:</b> {rule_name}",
            f"🕒 <b>Time:</b> {checked_at}",
            "",
            "If you received this, your Telegram channel connection is working.",
        ])
        details.append('Telegram sendMessage attempted')
        print('Telegram sendMessage attempted')
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10,
        )
        print(f"Telegram API status code: {response.status_code}")
        print(f"Telegram API response text: {response.text}")
        details.extend([
            f"Telegram API status code: {response.status_code}",
            f"Telegram API response text: {response.text}",
        ])
        try:
            response_data = response.json()
        except Exception:
            response_data = {}
        if not response.ok or not response_data.get('ok', False):
            telegram_error = response_data.get('description') or response.text or f'Telegram API error {response.status_code}'
            add_alert_log({
                'id': str(uuid.uuid4()),
                'alert_id': alert_id,
                'alert_name': alert.get('name', ''),
                'checked_at': checked_at,
                'status': 'test_error',
                'event_type': 'Error',
                'severity': 'error',
                'message': f'Test Telegram failed: {telegram_error}',
                'matches_count': 0,
                'sent_notifications': 0,
                'error': telegram_error,
                'listing': {},
                'reason': 'Telegram test failed.',
                'details': details,
            })
            return JSONResponse(status_code=400, content={'ok': False, 'message': f'Telegram test failed: {telegram_error}', 'error': telegram_error, 'telegram_status_code': response.status_code, 'telegram_response': response.text})
        add_alert_log({
            'id': str(uuid.uuid4()),
            'alert_id': alert_id,
            'alert_name': alert.get('name', ''),
            'checked_at': checked_at,
            'status': 'test_sent',
            'event_type': 'Sent',
            'severity': 'success',
            'message': 'Test Telegram message sent successfully',
            'matches_count': 0,
            'sent_notifications': 1,
            'error': '',
            'listing': {},
            'reason': 'Manual Test Telegram button clicked.',
            'details': [*details, 'Telegram success'],
        })
        return {'ok': True, 'message': 'Test message sent to Telegram channel.'}
    except Exception as exc:
        traceback.print_exc()
        error_text = str(exc)
        try:
            add_alert_log({
                'id': str(uuid.uuid4()),
                'alert_id': alert_id,
                'alert_name': alert.get('name', '') if alert else '',
                'checked_at': checked_at,
                'status': 'test_error',
                'event_type': 'Error',
                'severity': 'error',
                'message': f'Test Telegram failed: {error_text}',
                'matches_count': 0,
                'sent_notifications': 0,
                'error': error_text,
                'listing': {},
                'reason': 'Telegram test failed.',
                'details': [*details, f'Telegram failure: {error_text}'],
            })
        except Exception:
            traceback.print_exc()
        return JSONResponse(status_code=500, content={'ok': False, 'message': f'Telegram test failed: {error_text}', 'error': error_text})


@app.post('/api/alerts/{alert_id}/run-now')
def api_run_alert_now(alert_id: str):
    alerts = get_alerts()
    alert = next((a for a in alerts if a.get('id') == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail='Alert not found')
    bot_token = str(alert.get('telegram_bot_token', '') or get_settings().get('telegram_bot_token', '') or '').strip()
    chat_id = alerts_module.normalize_telegram_channel_id(alert.get('telegram_chat_id', '') or get_settings().get('telegram_chat_id', ''))
    add_alert_log({
        'id': str(uuid.uuid4()),
        'alert_id': alert_id,
        'alert_name': alert.get('name', ''),
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'run_started',
        'event_type': 'Match',
        'severity': 'warning',
        'message': 'Run now clicked. Rule loaded and scan started.',
        'matches_count': 0,
        'sent_notifications': 0,
        'error': '',
        'listing': {},
        'reason': 'Manual Run now button clicked.',
        'details': [
            'Button clicked: Run now',
            f"Alert ID: {alert_id}",
            f"Alert name: {alert.get('name', '') or alert_id}",
            f"Alert city: {alert.get('city') or ', '.join(alert.get('cities') or []) or 'All cities'}",
            f"Enabled: {'yes' if _is_alert_enabled(alert) else 'no'}",
            f"Rule loaded: {alert.get('name', '') or alert_id}",
            f"Rule enabled: {_is_alert_enabled(alert)}",
            f"Telegram bot token {'found' if bot_token else 'missing'}",
            f"Telegram channel ID {'found' if chat_id else 'missing'}",
            f"Normalized channel ID: {chat_id or '(missing)'}",
            'Scan started',
            f"Fast alert mode: {bool(alert.get('fast_alert_mode', True))}",
            f"Send all new plates: {bool(alert.get('send_all_new_plates'))}",
        ],
    })
    result = alerts_module.check_alert(alert)
    if not result.get('ok'):
        raise HTTPException(status_code=500, detail=result.get('error') or 'Run now failed')
    message = result.get('message') or f"Run completed: {result.get('sent', 0)} Telegram message(s) sent."
    return {**result, 'result': result, 'message': message}


@app.post('/api/alerts/{alert_id}/run')
def api_run_alert_now_alias(alert_id: str):
    return api_run_alert_now(alert_id)


@app.post('/api/alerts/{alert_id}/debug-scan')
def api_debug_alert_scan(alert_id: str):
    alerts = get_alerts()
    alert = next((a for a in alerts if a.get('id') == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail='Alert not found')
    result = alerts_module.check_alert(alert, dry_run=True)
    if not result.get('ok'):
        raise HTTPException(status_code=500, detail=result.get('error') or 'Debug scan failed')
    add_alert_log({
        'id': str(uuid.uuid4()),
        'alert_id': alert_id,
        'alert_name': alert.get('name', ''),
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'status': 'debug_scan',
        'event_type': 'Match',
        'severity': 'warning',
        'message': f"Debug scan completed for alert {alert.get('name', '') or alert_id}: {result.get('message', '')}".strip(),
        'matches_count': result.get('matched', 0),
        'sent_notifications': 0,
        'error': '',
        'listing': {},
        'reason': 'Manual Debug scan button clicked. No Telegram messages sent.',
        'details': [
            'Debug scan per rule only.',
            f"Alert ID: {alert_id}",
            f"Alert name: {alert.get('name', '') or alert_id}",
            f"Alert city: {alert.get('city') or ', '.join(alert.get('cities') or []) or 'All cities'}",
            f"Enabled: {'yes' if _is_alert_enabled(alert) else 'no'}",
            *result.get('decision_logs', [])[:100],
        ],
    })
    return {
        **result,
        'alert_id': alert_id,
        'alert_name': alert.get('name', '') or alert_id,
        'alert_city': alert.get('city') or ', '.join(alert.get('cities') or []) or 'All cities',
        'message': f"Debug scan for {alert.get('name', '') or alert_id}: {result.get('message', 'completed.')}",
    }


@app.post('/api/alerts/{alert_id}/force-test-listing')
def api_force_test_listing(alert_id: str):
    alerts = get_alerts()
    alert = next((a for a in alerts if a.get('id') == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail='Alert not found')

    bot_token = str(alert.get('telegram_bot_token', '') or get_settings().get('telegram_bot_token', '') or '').strip()
    chat_id = alerts_module.normalize_telegram_channel_id(alert.get('telegram_chat_id', '') or get_settings().get('telegram_chat_id', ''))
    checked_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    alert_cities = _normalize_alert_cities(alert)
    sample_row = {
        'city': alert_cities[0] if alert_cities else 'Sample City',
        'code': 'A',
        'plate_number': '89898',
        'price': 'AED 40,000',
        'seller_name': '?',
        'seller_username': '?',
        'phone_number': '?',
        'uploaded_date': datetime.now().strftime('%Y-%m-%d'),
        'uploaded_time': datetime.now().strftime('%H:%M:%S'),
        'listing_link': 'https://xplate.com/en/numbers/license-plates',
    }
    details = [
        'Button clicked: Force send test listing',
        f"Rule loaded: {alert.get('name', '') or alert_id}",
        f"Telegram bot token {'found' if bot_token else 'missing'}",
        f"Telegram channel ID {'found' if chat_id else 'missing'}",
        f"Normalized channel ID: {chat_id or '(missing)'}",
        'This action skips scraping, baseline, and duplicate checks.',
    ]

    try:
        alert_model = Alert(**alert)
        send_decision = alerts_module.send_telegram_plate_alert(bot_token, chat_id, alert_model, sample_row)
        if send_decision.get('skipped'):
            skip_reason = send_decision.get('skip_reason') or 'City mismatch'
            details.extend([
                f"alert_city: {alert.get('city') or ', '.join(alert.get('cities') or []) or 'All cities'}",
                f"listing_city: {sample_row.get('city') or '?'}",
                f"normalized_alert_city: {send_decision.get('normalized_alert_city') or 'All cities'}",
                f"normalized_listing_city: {send_decision.get('normalized_listing_city') or '?'}",
                "city_matched: no",
                "will_send: no",
                f"skip_reason: {skip_reason}",
            ])
            add_alert_log({
                'id': str(uuid.uuid4()),
                'alert_id': alert_id,
                'alert_name': alert.get('name', ''),
                'checked_at': checked_at,
                'status': 'force_test_skipped',
                'event_type': 'Skipped',
                'severity': 'warning',
                'message': f'Force send test listing skipped: {skip_reason}',
                'matches_count': 0,
                'sent_notifications': 0,
                'error': '',
                'listing': sample_row,
                'reason': skip_reason,
                'details': details,
            })
            return {
                'ok': True,
                'total_scraped': 0,
                'matched': 0,
                'new_after_baseline': 0,
                'skipped_baseline': 0,
                'skipped_duplicate': 0,
                'skipped_old': 0,
                'eligible_to_send': 0,
                'sent': 0,
                'failed': 0,
                'message': f'Force test listing skipped: {skip_reason}',
            }
        details.append('Telegram request sent through city-safe plate sender')
        telegram_response = send_decision.get('telegram_response') or {}
        details.append(f"Telegram API response ok: {telegram_response.get('ok')}")
        add_alert_log({
            'id': str(uuid.uuid4()),
            'alert_id': alert_id,
            'alert_name': alert.get('name', ''),
            'checked_at': checked_at,
            'status': 'force_test_sent',
            'event_type': 'Sent',
            'severity': 'success',
            'message': 'Force send test listing sent successfully',
            'matches_count': 1,
            'sent_notifications': 1,
            'error': '',
            'listing': sample_row,
            'reason': 'Manual Force send test listing button clicked.',
            'details': [*details, 'Telegram success'],
        })
        return {
            'ok': True,
            'total_scraped': 0,
            'matched': 1,
            'new_after_baseline': 1,
            'skipped_baseline': 0,
            'skipped_duplicate': 0,
            'skipped_old': 0,
            'eligible_to_send': 1,
            'sent': 1,
            'failed': 0,
            'message': 'Force test listing sent to Telegram channel.',
        }
    except Exception as exc:
        error_text = str(exc)
        add_alert_log({
            'id': str(uuid.uuid4()),
            'alert_id': alert_id,
            'alert_name': alert.get('name', ''),
            'checked_at': checked_at,
            'status': 'force_test_error',
            'event_type': 'Error',
            'severity': 'error',
            'message': f'Force send test listing failed: {error_text}',
            'matches_count': 1,
            'sent_notifications': 0,
            'error': error_text,
            'listing': sample_row,
            'reason': 'Telegram force test failed.',
            'details': [*details, f'Telegram failure: {error_text}'],
        })
        return {
            'ok': False,
            'total_scraped': 0,
            'matched': 1,
            'new_after_baseline': 1,
            'skipped_baseline': 0,
            'skipped_duplicate': 0,
            'skipped_old': 0,
            'eligible_to_send': 1,
            'sent': 0,
            'failed': 1,
            'message': f"Force test listing failed: {alerts_module.user_friendly_telegram_error(error_text)}",
            'errors': [error_text],
        }


@app.post('/api/alerts/{alert_id}/reset-baseline')
def api_reset_alert_baseline(alert_id: str):
    alerts = get_alerts()
    alert = next((a for a in alerts if a.get('id') == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail='Alert not found')
    reset_result = alerts_module.initialize_baseline(alert)
    alerts_module.clear_scheduler_cache()
    return {'alert': reset_result, 'message': 'Baseline reset. Future listings only.'}


@app.get('/api/alerts/logs')
def api_get_alert_logs():
    return {'logs': get_alert_logs()}


@app.post('/api/alerts/preview')
def api_alert_preview(alert: dict):
    cities = _normalize_alert_cities(alert)
    sample_row = {
        'city': cities[0] if cities else 'Sample City',
        'code': alert.get('code') or 'A',
        'plate_number': alert.get('plate_number') or alert.get('contains') or '89898',
        'price': alert.get('price_max') and f"AED {alert.get('price_max')}" or 'AED 40,000',
        'seller_name': 'Sample Seller',
        'seller_username': 'sample_seller',
        'phone_number': '+971500000000',
        'uploaded_date': datetime.now().strftime('%Y-%m-%d'),
        'uploaded_time': datetime.now().strftime('%H:%M:%S'),
        'listing_link': 'https://xplate.com/en/numbers/license-plates',
    }
    return {'message': alerts_module.build_telegram_message(Alert(**alert), sample_row)}


@app.delete('/api/alerts/logs')
def api_clear_alert_logs():
    clear_alert_logs()
    return {'ok': True}


@app.get('/api/instagram/settings')
def api_get_instagram_settings():
    return {'settings': instagram_monitor.get_instagram_settings()}


@app.post('/api/instagram/settings')
def api_save_instagram_settings(payload: dict):
    settings = payload.get('settings', payload)
    previous = instagram_monitor.get_instagram_settings()
    saved = instagram_monitor.save_instagram_settings(settings)
    enabled_turned_on = bool(saved.get('enabled')) and not bool(previous.get('enabled'))
    send_turned_on = bool(saved.get('enabled')) and bool(saved.get('send_all_new_posts')) and not bool(previous.get('send_all_new_posts'))
    if enabled_turned_on or send_turned_on:
        result = instagram_monitor.reset_instagram_baseline("Instagram baseline saved. Only future posts will be sent.")
        return {'settings': result.get('settings', instagram_monitor.get_instagram_settings()), 'message': result.get('message')}
    return {'settings': saved}


@app.post('/api/instagram/verify-provider')
def api_verify_instagram_provider(payload: dict | None = None):
    settings = (payload or {}).get('settings') if payload else None
    return instagram_monitor.verify_instagram_provider(settings)


@app.post('/api/instagram/run-now')
def api_run_instagram_now():
    result = instagram_monitor.run_instagram_check()
    if not result.get('ok'):
        raise HTTPException(status_code=500, detail=result.get('message') or 'Instagram check failed')
    return result


@app.post('/api/instagram/reset-baseline')
def api_reset_instagram_baseline():
    result = instagram_monitor.reset_instagram_baseline()
    if not result.get('ok'):
        raise HTTPException(status_code=500, detail=result.get('message') or 'Instagram baseline reset failed')
    return result


@app.post('/api/instagram/send-latest')
def api_send_latest_instagram():
    result = instagram_monitor.send_latest_from_all_accounts()
    if not result.get('ok'):
        raise HTTPException(status_code=500, detail=result.get('message') or 'Instagram latest post send failed')
    return result


@app.post('/api/instagram/debug-ocr')
def api_debug_instagram_ocr():
    result = instagram_monitor.debug_latest_ocr()
    if not result.get('ok'):
        raise HTTPException(status_code=400, detail=result.get('message') or 'Instagram OCR debug unavailable')
    return result


@app.get('/api/production/status')
def api_production_status():
    alerts = get_alerts()
    enabled_alerts = [alert for alert in alerts if _is_alert_enabled(alert)]
    last_scan_time = alerts_module.LAST_SCAN_TIME or max(
        (str(alert.get('last_scan_at') or alert.get('last_checked_at') or '') for alert in alerts),
        default='',
    )
    return {
        'backend': 'running',
        'environment': _runtime_environment(),
        'data_dir': str(DATA_DIR),
        'alerts_storage_path': str(ALERTS_PATH),
        'alerts_count': len(alerts),
        'enabled_alerts': len(enabled_alerts),
        'scheduler_running': alerts_module.scheduler_running(),
        'telegram_configured': _telegram_configured(),
        'last_scan_time': last_scan_time,
        'active_alert_ids': alerts_module.active_alert_ids(),
        'last_error': alerts_module.LAST_ERROR,
    }


@app.on_event('startup')
def start_alert_scheduler():
    try:
        alerts_module.start_scheduler()
    except Exception as exc:
        alerts_module.LAST_ERROR = f"Alert scheduler startup failed: {exc}"
        print(alerts_module.LAST_ERROR)
        traceback.print_exc()
    try:
        instagram_monitor.start_instagram_scheduler()
    except Exception as exc:
        print(f"Instagram scheduler startup failed: {exc}")
        traceback.print_exc()
    try:
        cleanup_days = get_config().cleanup_old_plates_days
        deleted = plate_tracking.cleanup_old_plates(cleanup_days)
        print(f"Startup cleanup: deleted {deleted} plate tracking records older than {cleanup_days} days")
    except Exception as exc:
        print(f"Startup cleanup failed: {exc}")
        traceback.print_exc()
    _log_production_startup()


@app.on_event('shutdown')
def stop_alert_scheduler():
    try:
        alerts_module.stop_scheduler()
    except Exception:
        pass
    try:
        instagram_monitor.stop_instagram_scheduler()
    except Exception:
        pass


@app.get("/api/dashboard/summary")
def dashboard_summary():
    history = get_history()
    favorites = get_favorites()
    sellers_data = seller_summary(LATEST_RESULTS)
    return {
        "summary": summarize(LATEST_RESULTS),
        "results_count": len(LATEST_RESULTS),
        "history_count": len(history),
        "favorites_count": len(favorites),
        "sellers_count": len(sellers_data),
    }


# ============================================================================
# PLATE TRACKING ADMIN ENDPOINTS
# ============================================================================

@app.get("/api/admin/plate-stats")
def api_plate_stats():
    """Get statistics about tracked plates."""
    stats = plate_tracking.get_plate_stats()
    return {
        "stats": stats,
        "timestamp": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    }


@app.get("/api/admin/plate-stats/{plate_id}")
def api_plate_info(plate_id: str):
    """Get detailed information about a specific plate."""
    info = plate_tracking.get_plate_info(*plate_id.split('_', 2))
    if not info:
        raise HTTPException(status_code=404, detail='Plate not found in tracking database')
    return {"plate_info": info}


@app.post("/api/admin/plate-tracking/cleanup")
def api_cleanup_old_plates(days: int = 30):
    """
    Delete plates not seen in the specified number of days.
    
    Args:
        days: Number of days to keep (default: 30)
    
    Returns:
        Number of records deleted
    """
    deleted = plate_tracking.cleanup_old_plates(days)
    return {
        "deleted_count": deleted,
        "message": f"Cleaned up {deleted} plates not seen in {days} days"
    }


@app.post("/api/admin/plate-tracking/reinit-db")
def api_reinit_tracking_db():
    """
    Reinitialize the plate tracking database (WARNING: Deletes all data).
    Requires admin confirmation via query parameter.
    """
    try:
        plate_tracking.init_db()
        return {"ok": True, "message": "Plate tracking database reinitialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reinitialize database: {str(e)}")


@app.get("/api/admin/config")
def api_get_config():
    """Get current alert configuration."""
    from .alert_config import get_config
    config = get_config()
    return {"config": config.to_dict()}


@app.post("/api/admin/config/reload")
def api_reload_config():
    """Reload configuration from environment and config file."""
    from .alert_config import reload_config
    reload_config()
    return {"ok": True, "message": "Configuration reloaded"}
