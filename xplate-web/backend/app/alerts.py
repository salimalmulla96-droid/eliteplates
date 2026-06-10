import html
import uuid
import time
import re
import traceback
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

import requests
from apscheduler.schedulers.background import BackgroundScheduler

from .models import Alert, AlertLog, SearchRequest
from .scraper import search_xplate, price_to_number, city_to_xplate_param, match_number_formats, normalize_number_formats, number_format_label
from .filters import apply_filters, sort_results
from .storage import DATA_DIR, ALERTS_PATH, get_alerts, save_alert, write_alerts, add_alert_log, get_alert_logs, clear_alert_logs, get_settings, trim_alert_runtime_state
from . import plate_tracking
from .alert_config import get_config

RUNNING_ALERTS: dict[str, bool] = {}
DISABLED_SKIP_LOGGED: set[str] = set()
SCHEDULER: BackgroundScheduler | None = None
LAST_SCAN_TIME = ''
LAST_ERROR: str | None = None
STOP_ALL_ALERTS_ACTIVE = False
STOP_ALL_REQUESTED_AT = ''
AUTO_MAX_PAGES_PER_SCAN = 20
AUTO_MAX_LISTINGS_PER_SCAN = 1000
AUTO_FRESH_LISTING_WINDOW_MINUTES = 15
LAST_PLATE_CLEANUP_DATE = ''


def _coerce_positive_int(value: Any, fallback: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except Exception:
        number = fallback
    number = max(number, minimum)
    if maximum is not None:
        number = min(number, maximum)
    return number


def _auto_max_pages_per_scan(alert: Alert) -> int:
    return _coerce_positive_int(getattr(alert, 'max_pages_per_scan', None), AUTO_MAX_PAGES_PER_SCAN, 1, 50)


def _auto_max_listings_per_scan(alert: Alert) -> int:
    return _coerce_positive_int(getattr(alert, 'max_listings_per_scan', None), AUTO_MAX_LISTINGS_PER_SCAN, 1, 2000)


def _auto_fresh_listing_window(alert: Alert) -> int:
    return _coerce_positive_int(getattr(alert, 'fresh_listing_window_minutes', None), AUTO_FRESH_LISTING_WINDOW_MINUTES, 1, 120)


def normalize_telegram_channel_id(chat_id: str | None) -> str:
    value = str(chat_id or '').strip()
    if value.startswith('https://t.me/'):
        value = value.replace('https://t.me/', '', 1)
    elif value.startswith('http://t.me/'):
        value = value.replace('http://t.me/', '', 1)
    elif value.startswith('t.me/'):
        value = value.replace('t.me/', '', 1)
    value = value.strip().strip('/')
    if value and not value.startswith('@') and not value.startswith('-100') and not value.lstrip('-').isdigit():
        value = f'@{value}'
    return value


def user_friendly_telegram_error(error_text: str) -> str:
    lower = str(error_text or '').lower()
    if 'chat not found' in lower:
        return 'Telegram channel not found. Make sure the channel ID is correct and the bot is added as an admin.'
    if 'unauthorized' in lower or 'invalid token' in lower:
        return 'Telegram bot token is invalid. Check the token from BotFather.'
    if 'forbidden' in lower or 'not enough rights' in lower or 'admin' in lower:
        return 'Telegram bot cannot post to this channel. Add the bot as an admin and allow it to post messages.'
    return str(error_text or 'Telegram request failed')


def send_telegram_message(bot_token: str, chat_id: str, message: str) -> dict[str, Any]:
    bot_token = str(bot_token or '').strip()
    chat_id = normalize_telegram_channel_id(chat_id)
    if not bot_token:
        raise ValueError('Telegram bot token missing')
    if not chat_id:
        raise ValueError('Telegram channel ID missing')
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    resp = requests.post(url, json=payload, timeout=10)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        details = ''
        try:
            details = resp.json().get('description', '')
        except Exception:
            details = resp.text
        friendly = user_friendly_telegram_error(details)
        raise ValueError(f"{friendly} Telegram API error: {details}") from exc
    return resp.json()


def _listing_key(row: dict[str, Any]) -> str:
    for field in ('listing_id', 'id', 'plate_id'):
        value = str(row.get(field, '') or '').strip()
        if value:
            return f"id:{value}"
    link = str(row.get('listing_link', '') or '').strip()
    if not link:
        link = str(row.get('listing_url', '') or row.get('url', '') or '').strip()
    if link:
        match = re.search(r"/(\d+)(?:[-/]|$)", link)
        if match:
            return f"id:{match.group(1)}"
        return f"url:{link}"
    return "|".join([
        'detected',
        str(row.get('source_url', '') or '').strip(),
        str(row.get('city', '') or '').strip(),
        str(row.get('code', '') or '').strip(),
        str(row.get('plate_number', '') or '').strip(),
        str(row.get('price', '') or '').strip(),
        str(row.get('seller_username', '') or '').strip(),
        str(row.get('listing_link', '') or '').strip(),
    ])


def _listing_url(row: dict[str, Any]) -> str:
    return str(row.get('listing_link') or row.get('listing_url') or row.get('url') or '').strip()


def _extract_listing_id(row: dict[str, Any]) -> int | None:
    for field in ('listing_id', 'id', 'plate_id'):
        value = str(row.get(field, '') or '').strip()
        if value.isdigit():
            return int(value)
    link = _listing_url(row)
    if link:
        match = re.search(r"/license-plates/(\d+)(?:[-/]|$)", link)
        if not match:
            match = re.search(r"/(\d+)(?:[-/]|$)", link)
        if match:
            return int(match.group(1))
    return None


def _listing_id(row: dict[str, Any]) -> str:
    listing_id = _extract_listing_id(row)
    return str(listing_id) if listing_id is not None else ''


def parse_relative_posted_time(posted_text: str | None) -> dict[str, Any]:
    text = str(posted_text or '').strip().lower()
    result = {'matched': False, 'value': None, 'unit': '', 'minutes': None, 'auto_send_unit': False}
    match = re.search(r'\b(?:(\d+)\s+)?(second|seconds|minute|minutes|hour|hours|day|days)\s+ago\b', text)
    if match:
        value = int(match.group(1) or 1)
        unit = match.group(2)
        if unit.startswith('second'):
            minutes = 0
            auto_send_unit = True
        elif unit.startswith('minute'):
            minutes = value
            auto_send_unit = True
        elif unit.startswith('hour'):
            minutes = value * 60
            auto_send_unit = False
        else:
            minutes = value * 1440
            auto_send_unit = False
        result.update({'matched': True, 'value': value, 'unit': unit, 'minutes': minutes, 'auto_send_unit': auto_send_unit})
    return result


def is_recent_posted_text(posted_text: str | None, window_minutes: int = 15) -> bool:
    parsed = parse_relative_posted_time(posted_text)
    if not parsed.get('matched') or not parsed.get('auto_send_unit'):
        return False
    return int(parsed.get('minutes') or 0) <= max(int(window_minutes or 15), 1)


def _format_phone(phone: str | None) -> str:
    phone = str(phone or '').strip()
    if not phone or phone in {'', '?', 'N/A', 'Not available', 'Not collected in fast mode'}:
        return '?'
    return phone


def _resolve_telegram_credentials(alert: Alert) -> tuple[str, str]:
    bot_token = str(alert.telegram_bot_token or '').strip()
    chat_id = normalize_telegram_channel_id(alert.telegram_chat_id)
    if bot_token and chat_id:
        return bot_token, chat_id
    settings = get_settings()
    bot_token = bot_token or str(settings.get('telegram_bot_token', '') or '').strip()
    chat_id = chat_id or normalize_telegram_channel_id(settings.get('telegram_chat_id', ''))
    return bot_token, chat_id


def _html_escape(value: str | None) -> str:
    return html.escape(str(value or ''), quote=False)


def _clean_city(city: str | None) -> str:
    text = str(city or '').strip()
    return text.title() if text else '?'


def _is_enabled_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {'true', '1', 'yes', 'enabled', 'on'}
    return bool(value)


def _alert_cities(alert: Alert) -> list[str]:
    cities = [str(city or '').strip() for city in (alert.cities or []) if str(city or '').strip()]
    if not cities and alert.city:
        cities = [str(alert.city).strip()]
    return [city for city in cities if city.lower() not in {'all', 'all cities'}]


CITY_ALIASES = {
    'dubai': 'dubai',
    'دبي': 'dubai',
    'abu dhabi': 'abu dhabi',
    'abu-dhabi': 'abu dhabi',
    'abudhabi': 'abu dhabi',
    'أبوظبي': 'abu dhabi',
    'ابوظبي': 'abu dhabi',
    'sharjah': 'sharjah',
    'الشارقة': 'sharjah',
    'ajman': 'ajman',
    'عجمان': 'ajman',
    'ras al khaimah': 'ras al khaimah',
    'ras-al-khaimah': 'ras al khaimah',
    'rak': 'ras al khaimah',
    'r a k': 'ras al khaimah',
    'r.a.k': 'ras al khaimah',
    'رأس الخيمة': 'ras al khaimah',
    'راس الخيمة': 'ras al khaimah',
    'umm al quwain': 'umm al quwain',
    'umm-al-quwain': 'umm al quwain',
    'umm al qaiwain': 'umm al quwain',
    'أم القيوين': 'umm al quwain',
    'ام القيوين': 'umm al quwain',
    'fujairah': 'fujairah',
    'الفجيرة': 'fujairah',
}


def normalize_city(value: str | None) -> str:
    text = str(value or '').strip().lower()
    if not text or text in {'all', 'all cities'}:
        return ''
    text = text.replace('-', ' ').replace('_', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    dotted_alias = CITY_ALIASES.get(text)
    if dotted_alias:
        return dotted_alias
    text_without_dots = re.sub(r'[.]', ' ', text)
    text_without_dots = re.sub(r'\s+', ' ', text_without_dots).strip()
    if text_without_dots in CITY_ALIASES:
        return CITY_ALIASES[text_without_dots]
    compact = re.sub(r'[\s.]', '', text)
    if compact in CITY_ALIASES:
        return CITY_ALIASES[compact]
    return CITY_ALIASES.get(text, text)


def _alert_city_filters(alert: Alert) -> list[str]:
    filters: list[str] = []
    for city in _alert_cities(alert):
        normalized = normalize_city(city)
        if normalized and normalized not in filters:
            filters.append(normalized)
    return filters


def _city_filter_decision(alert: Alert, row: dict[str, Any]) -> tuple[bool, str, str, str]:
    alert_cities = _alert_city_filters(alert)
    alert_city = ', '.join(alert_cities)
    listing_city = normalize_city(row.get('city'))
    if not alert_cities:
        return True, '', alert_city or 'All cities', listing_city
    if not listing_city:
        return False, 'City missing for city-specific alert', alert_city, listing_city
    if listing_city not in alert_cities:
        return False, 'City mismatch', alert_city, listing_city
    return True, '', alert_city, listing_city


def listing_matches_alert_city(alert: Alert, listing: dict[str, Any]) -> bool:
    return _city_filter_decision(alert, listing)[0]


def _city_send_decision_lines(alert: Alert, listing: dict[str, Any], will_send: bool, skip_reason: str = '') -> list[str]:
    city_matched, decision_reason, normalized_alert_city, normalized_listing_city = _city_filter_decision(alert, listing)
    raw_alert_city = alert.city or ', '.join(alert.cities or []) or 'All cities'
    raw_listing_city = listing.get('city') or ''
    return [
        f"alert_city: {raw_alert_city or 'All cities'}",
        f"listing_city: {raw_listing_city or '?'}",
        f"normalized_alert_city: {normalized_alert_city or 'All cities'}",
        f"normalized_listing_city: {normalized_listing_city or '?'}",
        f"city_matched: {'yes' if city_matched else 'no'}",
        f"will_send: {'yes' if will_send else 'no'}",
        f"skip_reason: {skip_reason or decision_reason or 'none'}",
    ]


def _city_to_scraper_value(city: str) -> str:
    return normalize_city(city)


def _ensure_alert_city_fields(alert_dict: dict[str, Any]) -> dict[str, Any]:
    alert_copy = dict(alert_dict or {})
    city = str(alert_copy.get('city') or '').strip()
    cities = [
        str(value or '').strip()
        for value in (alert_copy.get('cities') or [])
        if str(value or '').strip()
    ]
    cities = [value for value in cities if value.lower() not in {'all', 'all cities'}]
    if (not city or city.lower() in {'all', 'all cities'}) and cities:
        alert_copy['city'] = cities[0]
    elif city and city.lower() not in {'all', 'all cities'} and not cities:
        alert_copy['cities'] = [city]
    return alert_copy


def _alert_city_log_value(alert: Alert) -> str:
    return str(alert.city or ', '.join(alert.cities or []) or 'All cities').strip() or 'All cities'


def _alert_display_name(alert: Alert) -> str:
    return str(alert.name or alert.id or 'Untitled alert').strip()


def _alert_identity_lines(alert: Alert) -> list[str]:
    return [
        f"Alert ID: {alert.id or '(missing)'}",
        f"Alert name: {_alert_display_name(alert)}",
        f"Alert city: {_alert_city_log_value(alert)}",
        f"Enabled: {'yes' if alert.enabled else 'no'}",
    ]


def _log_scraper_city(alert: Alert, city: str) -> None:
    city_for_url = city or alert.city or ''
    print("Alert ID:", alert.id or '(missing)')
    print("Alert name:", _alert_display_name(alert))
    print("Alert city:", _alert_city_log_value(alert))
    print("Enabled:", 'yes' if alert.enabled else 'no')
    print("Xplate city param:", city_to_xplate_param(city_for_url))


def _clean_price(price: str | None) -> str:
    text = str(price or '').strip()
    if not text or text in {'?', 'Not available'}:
        return '?'
    if 'hidden' in text.lower():
        return '?'
    text = ' '.join(text.replace('AED AED', 'AED').split())
    if text.upper().startswith('AED'):
        amount = text[3:].strip()
        return f"AED {amount}" if amount else '?'
    return f"AED {text}"


def _clean_username(username: str | None) -> str:
    text = str(username or '').strip()
    if not text or text in {'?', 'Not available', 'Unknown', 'Not collected in fast mode'}:
        return '?'
    return text if text.startswith('@') else f'@{text}'


def _clean_seller_name(name: str | None) -> str:
    text = str(name or '').strip()
    return text if text and text not in {'?', 'Not available', 'Unknown', 'Not collected in fast mode'} else '?'


def _posted_when(row: dict[str, Any]) -> str:
    age_text = str(row.get('age_text') or '').strip()
    if age_text and age_text not in {'?', 'Not available', 'Not collected in fast mode'}:
        return age_text
    value = f"{row.get('uploaded_date') or ''} {row.get('uploaded_time') or ''}".strip()
    return value if value and value != 'Not available Not available' else '?'


def _format_uae_datetime(value: datetime) -> str:
    value = value.astimezone(ZoneInfo('Asia/Dubai'))
    hour = value.strftime('%I').lstrip('0') or '0'
    minute = value.strftime('%M')
    meridiem = value.strftime('%p')
    return f"{hour}:{minute} {meridiem} on {value.day}/{value.month}/{value.year}"


def _exact_posted_time(row: dict[str, Any]) -> str:
    date_text = str(row.get('uploaded_date') or '').strip()
    time_text = str(row.get('uploaded_time') or '').strip()
    if date_text and time_text and date_text != 'Not available' and time_text != 'Not available':
        for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                parsed = datetime.strptime(f'{date_text} {time_text}', pattern)
                return _format_uae_datetime(parsed.replace(tzinfo=ZoneInfo('Asia/Dubai')))
            except ValueError:
                continue

    relative = parse_relative_posted_time(row.get('age_text'))
    if relative.get('matched') and relative.get('minutes') is not None:
        posted_at = datetime.now(ZoneInfo('Asia/Dubai')) - timedelta(minutes=int(relative.get('minutes') or 0))
        return _format_uae_datetime(posted_at)

    return '?'


def _rule_summary(alert: Alert) -> str:
    if alert.send_all_new_plates:
        return 'all new plates'
    parts = []
    if alert.plate_number:
        parts.append(f"{alert.search_mode} {alert.plate_number}")
    if alert.contains:
        parts.append(f"contains {alert.contains}")
    if alert.starts_with:
        parts.append(f"starts with {alert.starts_with}")
    if alert.ends_with:
        parts.append(f"ends with {alert.ends_with}")
    if alert.code:
        parts.append(f"code {alert.code}")
    if alert.cities:
        parts.append(f"cities {', '.join(alert.cities)}")
    selected_formats = normalize_number_formats(alert.number_formats, fallback=alert.number_format)
    if selected_formats:
        parts.append(', '.join(number_format_label(item) for item in selected_formats))
    if alert.price_max:
        parts.append(f"under AED {alert.price_max}")
    return ', '.join(parts) or alert.name or 'saved alert rule'


def _icon(alert: Alert, emoji: str, fallback: str = '') -> str:
    return emoji if alert.telegram_emojis else fallback


def _match_reason(alert: Alert) -> str:
    if alert.send_all_new_plates:
        return 'Sent because Send every new plate to Telegram is enabled and this listing was published after your baseline.'
    return f"Sent because this listing matched your saved alert rule: {_rule_summary(alert)}."


def _format_match_decision(alert: Alert, row: dict[str, Any]) -> dict[str, Any]:
    return match_number_formats(row.get('plate_number', ''), alert.number_formats, fallback=alert.number_format)


def build_telegram_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    title = _html_escape(alert.telegram_message_title or 'New Plate Alert')
    city = _html_escape(_clean_city(row.get('city')))
    code = _html_escape(str(row.get('code') or '?').strip() or '?')
    number = _html_escape(str(row.get('plate_number') or '?').strip() or '?')
    price = _html_escape(_clean_price(row.get('price')))
    seller_name = _html_escape(_clean_seller_name(row.get('seller_name')))
    seller_username = _html_escape(_clean_username(row.get('seller_username')))
    phone = _html_escape(_format_phone(row.get('phone_number')))
    if str(row.get('phone_number') or '') == 'Not collected in fast mode':
        phone = 'Not collected in fast mode'
    posted = _html_escape(_posted_when(row))
    detected = _html_escape(datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
    listing_link = str(row.get('listing_link') or '').strip()
    safe_link = html.escape(listing_link, quote=True)
    alert_mode = 'Send All New Plates' if alert.send_all_new_plates else 'Specific Rule Match'
    reason = _html_escape(_match_reason(alert))
    plate_label = f"{city} {code} {number}".replace('  ', ' ')

    if alert.telegram_compact_mode:
        lines = [
            f"{_icon(alert, '🚨')} <b>{title}:</b> {plate_label}".strip(),
            f"{_icon(alert, '💰')} <b>Price:</b> {price}".strip(),
        ]
        if alert.telegram_include_seller_details:
            lines.extend([
                f"{_icon(alert, '👤')} <b>Seller:</b> {seller_name}".strip(),
                f"{_icon(alert, '📞')} <b>Phone:</b> {phone}".strip(),
            ])
        if safe_link:
            lines.append(f"{_icon(alert, '🔗')} <a href=\"{safe_link}\">Open Listing</a>".strip())
        return '\n'.join(lines)

    lines = [
        f"{_icon(alert, '🚨')} <b>{title}</b>".strip(),
        '',
        '━━━━━━━━━━━━━━',
        f"{_icon(alert, '🏷️')} <b>Plate</b>".strip(),
        f"<b>{plate_label}</b>",
        '',
        f"{_icon(alert, '📍')} <b>City:</b> {city}".strip(),
        f"{_icon(alert, '🔢')} <b>Code:</b> {code}".strip(),
        f"{_icon(alert, '🔎')} <b>Alert Mode:</b> {alert_mode}".strip(),
        '━━━━━━━━━━━━━━',
        '',
        f"{_icon(alert, '💰')} <b>Price:</b> {price}".strip(),
    ]
    if alert.telegram_include_seller_details:
        if alert.fast_alert_mode:
            seller_name = 'Not collected in fast mode'
            seller_username = 'Not collected in fast mode'
            phone = 'Not collected in fast mode'
        lines.extend([
            '',
            f"{_icon(alert, '👤')} <b>Seller:</b> {seller_name}".strip(),
            f"{_icon(alert, '🔗')} <b>Username:</b> {seller_username}".strip(),
            f"{_icon(alert, '📞')} <b>Phone:</b> {phone}".strip(),
        ])
    lines.extend(['', f"{_icon(alert, '🕒')} <b>Posted:</b> {posted}".strip()])
    if alert.telegram_include_detected_time:
        lines.append(f"{_icon(alert, '📡')} <b>Checked:</b> {detected}".strip())
    if alert.telegram_include_match_reason:
        lines.extend(['', f"{_icon(alert, '✅')} <b>Reason</b>".strip(), reason])
    if safe_link:
        lines.extend(['', f"{_icon(alert, '🔗')} <a href=\"{safe_link}\">Open Listing</a>".strip()])
    return '\n'.join(lines)


def build_telegram_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    title = _html_escape(alert.telegram_message_title or 'New Plate Alert')
    city = _html_escape(_clean_city(row.get('city')))
    code = _html_escape(str(row.get('code') or '?').strip() or '?')
    number = _html_escape(str(row.get('plate_number') or '?').strip() or '?')
    price = _html_escape(_clean_price(row.get('price')))
    seller_name = _html_escape(_clean_seller_name(row.get('seller_name')))
    seller_username = _html_escape(_clean_username(row.get('seller_username')))
    phone = _html_escape(_format_phone(row.get('phone_number')))
    posted = _html_escape(_posted_when(row))
    detected = _html_escape(datetime.now(ZoneInfo('Asia/Dubai')).strftime('%Y-%m-%d %H:%M UAE'))
    listing_link = str(row.get('listing_link') or '').strip()
    safe_link = html.escape(listing_link, quote=True)
    alert_mode = 'Send All New Plates' if alert.send_all_new_plates else 'Specific Rule Match'
    rule_name = alert.name or _rule_summary(alert)
    reason = _html_escape(f"Sent because this listing matched your saved alert rule: {rule_name}.")
    plate_label = f"{city} {code} {number}".replace('  ', ' ')
    featured = _html_escape('Yes' if row.get('featured') else 'No')
    status = _html_escape('Sold' if row.get('sold') else 'Available')
    reason = _html_escape(f"Sent because this listing was newly posted within the fresh listing window and matched your saved alert rule: {rule_name}.")

    lines = [
        f"🚨 <b>{title}</b>",
        "",
        "━━━━━━━━━━━━━━",
        "🏷️ <b>Plate</b>",
        f"<b>{plate_label}</b>",
        "",
        f"📍 <b>City:</b> {city}",
        f"🔢 <b>Code:</b> {code}",
        f"⭐ <b>Featured:</b> {featured}",
        f"📌 <b>Status:</b> {status}",
        f"🔎 <b>Alert Mode:</b> {alert_mode}",
        "━━━━━━━━━━━━━━",
        "",
        f"💰 <b>Price:</b> {price}",
    ]
    if alert.telegram_include_seller_details:
        lines.extend([
            "",
            f"👤 <b>Seller:</b> {seller_name}",
            f"🔗 <b>Username:</b> {seller_username}",
            f"📞 <b>Phone:</b> {phone}",
        ])
    lines.extend(["", f"🕒 <b>Posted:</b> {posted}"])
    if alert.telegram_include_detected_time:
        lines.append(f"📡 <b>Checked:</b> {detected}")
    if alert.telegram_include_match_reason:
        lines.extend(["", "✅ <b>Reason</b>", reason])
    if safe_link:
        lines.extend(["", "🔗 <b>Open Listing</b>", safe_link])
    return "\n".join(lines)

    if alert.telegram_compact_mode:
        lines = [
            f"🚨 <b>{title}:</b> {plate_label}",
            f"💰 <b>Price:</b> {price}",
            f"⭐ <b>Featured:</b> {featured}",
            f"📌 <b>Status:</b> {status}",
        ]
        if alert.telegram_include_seller_details:
            lines.extend([
                f"👤 <b>Seller:</b> {seller_name}",
                f"🔗 <b>Username:</b> {seller_username}",
                f"📞 <b>Phone:</b> {phone}",
            ])
        lines.extend([f"🕒 <b>Posted:</b> {posted}", f"📡 <b>Checked:</b> {detected}"])
        if safe_link:
            lines.append(f"🔗 <a href=\"{safe_link}\">Open Listing</a>")
        return '\n'.join(lines)

    lines = [
        f"🚨 <b>{title}</b>",
        '',
        '━━━━━━━━━━━━━━',
        '🏷️ <b>Plate</b>',
        f"<b>{plate_label}</b>",
        '',
        f"📍 <b>City:</b> {city}",
        f"🔢 <b>Code:</b> {code}",
        f"⭐ <b>Featured:</b> {featured}",
        f"📌 <b>Status:</b> {status}",
        f"🔎 <b>Alert Mode:</b> {alert_mode}",
        '━━━━━━━━━━━━━━',
        '',
        f"💰 <b>Price:</b> {price}",
    ]
    if alert.telegram_include_seller_details:
        lines.extend([
            '',
            f"👤 <b>Seller:</b> {seller_name}",
            f"🔗 <b>Username:</b> {seller_username}",
            f"📞 <b>Phone:</b> {phone}",
        ])
    lines.extend(['', f"🕒 <b>Posted:</b> {posted}"])
    if alert.telegram_include_detected_time:
        lines.append(f"📡 <b>Checked:</b> {detected}")
    if alert.telegram_include_match_reason:
        lines.extend(['', "✅ <b>Reason</b>", reason])
    if safe_link:
        lines.extend(['', "🔗 <b>Open Listing</b>", safe_link])
    return '\n'.join(lines)


def build_telegram_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    title = _html_escape(alert.telegram_message_title or 'New Plate Alert')
    city = _html_escape(_clean_city(row.get('city')))
    code = _html_escape(str(row.get('code') or '?').strip() or '?')
    number = _html_escape(str(row.get('plate_number') or '?').strip() or '?')
    price = _html_escape(_clean_price(row.get('price')))
    seller_name = _html_escape(_clean_seller_name(row.get('seller_name')))
    seller_username = _html_escape(_clean_username(row.get('seller_username')))
    phone = _html_escape(_format_phone(row.get('phone_number')))
    posted = _html_escape(_posted_when(row))
    listing_link = str(row.get('listing_link') or row.get('listing_url') or row.get('url') or '').strip()
    safe_link = html.escape(listing_link, quote=False)
    plate_label = f"{city} {code} {number}".replace('  ', ' ').strip()
    featured = _html_escape('Yes' if row.get('featured') else 'No')
    status = _html_escape('Sold' if row.get('sold') else 'Available')

    lines = [
        f"🚨 <b>{title}</b>",
        "",
        "━━━━━━━━━━━━━━",
        "🏷️ <b>Plate</b>",
        f"<b>{plate_label}</b>",
        "",
        f"📍 <b>City:</b> {city}",
        f"🔢 <b>Code:</b> {code}",
        f"⭐ <b>Featured:</b> {featured}",
        f"📌 <b>Status:</b> {status}",
        "━━━━━━━━━━━━━━",
        "",
        f"💰 <b>Price:</b> {price}",
        "",
        f"👤 <b>Seller:</b> {seller_name}",
        f"🔗 <b>Username:</b> {seller_username}",
        f"📞 <b>Phone:</b> {phone}",
        "",
        f"🕒 <b>Posted:</b> {posted}",
    ]
    if safe_link:
        lines.extend(["", "🔗 <b>Open Listing</b>", safe_link])
    return "\n".join(lines)


def build_telegram_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    city = _html_escape(_clean_city(row.get('city')))
    code = _html_escape(str(row.get('code') or '?').strip() or '?')
    number = _html_escape(str(row.get('plate_number') or '?').strip() or '?')
    posted = _html_escape(_exact_posted_time(row))
    listing_url = str(row.get('listing_link') or row.get('listing_url') or row.get('url') or '').strip()
    safe_url = html.escape(listing_url, quote=True)
    plate_label = f"{city} {code} {number}".replace('  ', ' ').strip()
    link = f'<a href="{safe_url}">Link</a>' if safe_url else 'Link'
    return "\n".join([
        f"🏷️ Plate: {plate_label}",
        f"🕒 Posted: {posted}",
        "",
        f"🔗 Link: {link}",
    ])


def _telegram_price(row: dict[str, Any]) -> str:
    text = str(row.get('price') or '').strip()
    if not text or text in {'?', 'Not available'}:
        return '?'
    if any(marker in text.lower() for marker in ('hidden', 'call for price', 'price on request')):
        return 'Price hidden'
    return _clean_price(text)


def build_telegram_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    city = _html_escape(_clean_city(row.get('city')))
    code = _html_escape(str(row.get('code') or '?').strip() or '?')
    number = _html_escape(str(row.get('plate_number') or '?').strip() or '?')
    price = _html_escape(_telegram_price(row))
    posted = _html_escape(_exact_posted_time(row))
    listing_url = str(row.get('listing_link') or row.get('listing_url') or row.get('url') or '').strip()
    safe_url = html.escape(listing_url, quote=True)
    plate_label = f"{city} {code} {number}".replace('  ', ' ').strip()
    link = f'<a href="{safe_url}">Link</a>' if safe_url else 'Link'
    return "\n".join([
        f"🏷️ Plate: {plate_label}",
        f"💰 Price: {price}",
        f"🕒 Posted: {posted}",
        "",
        f"🔗 Link: {link}",
    ])


def send_telegram_plate_alert(bot_token: str, chat_id: str, alert: Alert, listing: dict[str, Any], plate_info: dict[str, Any] | None = None) -> dict[str, Any]:
    print("Sending Telegram for alert:", _alert_display_name(alert))
    print("Alert ID:", alert.id or '(missing)')
    print("Alert city:", _alert_city_log_value(alert))
    print("Listing city:", listing.get('city') or '?')
    if stop_all_active():
        print("Telegram skipped: emergency stop-all is active")
        return {
            'sent': False,
            'skipped': True,
            'skip_reason': 'Emergency stop-all is active',
            'telegram_response': {},
        }
    storage_alert = _storage_alert(str(alert.id or '')) if alert.id else None
    if alert.id and not (storage_alert and _is_enabled_value(storage_alert.get('enabled'))):
        print("Telegram skipped: alert is disabled or missing in storage")
        return {
            'sent': False,
            'skipped': True,
            'skip_reason': 'Alert is disabled or missing in storage',
            'telegram_response': {},
        }
    if storage_alert and _listing_already_sent(storage_alert, listing):
        print("Telegram skipped: listing was already sent")
        return {
            'sent': False,
            'skipped': True,
            'skip_reason': 'Listing was already sent',
            'telegram_response': {},
        }
    city_matched, skip_reason, normalized_alert_city, normalized_listing_city = _city_filter_decision(alert, listing)
    if not city_matched:
        print("Telegram skipped by final city guard:", skip_reason or 'City mismatch')
        return {
            'sent': False,
            'skipped': True,
            'skip_reason': skip_reason or 'City mismatch',
            'city_matched': False,
            'normalized_alert_city': normalized_alert_city,
            'normalized_listing_city': normalized_listing_city,
            'telegram_response': {},
        }
    format_decision = _format_match_decision(alert, listing)
    if not format_decision.get('matched'):
        skip_reason = format_decision.get('skip_reason') or 'number format mismatch'
        print("Telegram skipped by final number format guard:", skip_reason)
        return {
            'sent': False,
            'skipped': True,
            'skip_reason': skip_reason,
            'city_matched': True,
            'normalized_alert_city': normalized_alert_city,
            'normalized_listing_city': normalized_listing_city,
            'telegram_response': {},
        }
    bot_token = str(bot_token or '').strip()
    chat_id = normalize_telegram_channel_id(chat_id)
    if not bot_token or not chat_id:
        skip_reason = 'Telegram is not configured'
        print("Telegram skipped:", skip_reason)
        return {
            'sent': False,
            'skipped': True,
            'skip_reason': skip_reason,
            'city_matched': True,
            'normalized_alert_city': normalized_alert_city,
            'normalized_listing_city': normalized_listing_city,
            'telegram_response': {},
        }
    config = get_config()
    city = str(listing.get('city', '') or '').strip()
    code = str(listing.get('code', '') or '').strip()
    plate_number = str(listing.get('plate_number', '') or '').strip()
    if config.enable_dedup_messages and city and plate_number:
        should_send, existing_plate = plate_tracking.should_send_telegram(
            city,
            code,
            plate_number,
            cooldown_seconds=config.duplicate_cooldown_seconds,
            alert_id=alert.id,
        )
        if not should_send:
            skip_reason = f"Duplicate/cooldown protection active for {config.duplicate_cooldown_seconds} seconds"
            print("Telegram skipped:", skip_reason)
            return {
                'sent': False,
                'skipped': True,
                'skip_reason': skip_reason,
                'city_matched': True,
                'normalized_alert_city': normalized_alert_city,
                'normalized_listing_city': normalized_listing_city,
                'plate_info': existing_plate,
                'telegram_response': {},
            }
    message = build_telegram_message(alert, listing, plate_info)
    response = send_telegram_message(bot_token, chat_id, message)
    return {
        'sent': True,
        'skipped': False,
        'skip_reason': '',
        'city_matched': True,
        'normalized_alert_city': normalized_alert_city,
        'normalized_listing_city': normalized_listing_city,
        'telegram_response': response,
    }


def _format_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    return build_telegram_message(alert, row, plate_info)


def _legacy_format_message(alert: Alert, row: dict[str, Any], plate_info: dict[str, Any] | None = None) -> str:
    seller_name = _html_escape(row.get('seller_name') or 'Not available')
    seller_username = _html_escape(row.get('seller_username') or 'Not available')
    price = _html_escape(row.get('price') or 'Price not listed')
    phone = _html_escape(_format_phone(row.get('phone_number')))
    listing_link = _html_escape(row.get('listing_link') or 'Not available')
    plate_number = _html_escape(row.get('plate_number') or '?')
    city = _html_escape(row.get('city') or '?')
    code = _html_escape(row.get('code') or '?')
    posted_when = _html_escape(f"{row.get('uploaded_date') or '?'} {row.get('uploaded_time') or '?'}")
    if alert.send_all_new_plates:
        is_new_plate = not plate_info or plate_info.get('total_releases', 1) == 1
        lines = [
            '🚨 <b>New Plate Published</b>' if is_new_plate else '🚨 <b>Plate Released Again</b>',
            '',
            f'🏷️ <b>Plate:</b> {city} {code} {plate_number}',
            f'📍 <b>City:</b> {city}',
            f'🔢 <b>Code:</b> {code}',
            '✨ <b>Alert Mode:</b> Send All New Plates',
            '',
            f'💰 <b>Price:</b> AED {price}' if price != 'Price not listed' else '💰 <b>Price:</b> Price not listed',
            '',
            f'👤 <b>Seller:</b> {seller_name}',
            f'🔗 <b>Username:</b> {seller_username}',
            f'📞 <b>Phone:</b> {phone}',
            '',
            f'🕒 <b>Posted:</b> {posted_when}',        ]
        
        # Add release info if it's a repost
        total_releases = plate_info.get('total_releases', 1) if plate_info else 1
        last_seen = plate_info.get('last_seen_at') if plate_info else None
        if not is_new_plate and plate_info:
            lines.extend([
                '',
                f'🔁 <b>Total Releases Seen:</b> {total_releases}',
            ])
            if last_seen:
                lines.append(f'⏰ <b>Last Seen:</b> {last_seen}')
        
                lines.extend([
                    '',
            '✅ <b>Reason:</b> Sent because “Send every new plate to Telegram” is enabled.',
            '',
            f'🔗 <a href="{listing_link}">Open Listing</a>',
                ])
    else:
        rule_name = _html_escape(alert.plate_number or alert.contains or alert.name or 'Saved alert')
        is_new_plate = not plate_info or plate_info.get('total_releases', 1) == 1
        lines = [
            '🚨 <b>New Matching Plate Alert</b>' if is_new_plate else '🚨 <b>Plate Released Again</b>',
            '',
            f'🏷️ <b>Plate:</b> {city} {code} {plate_number}',
            f'📍 <b>City:</b> {city}',
            f'🔢 <b>Code:</b> {code}',
            f'✨ <b>Matched Rule:</b> {rule_name}',
            '',
            f'💰 <b>Price:</b> AED {price}' if price != 'Price not listed' else '💰 <b>Price:</b> Price not listed',
            '',
            f'👤 <b>Seller:</b> {seller_name}',
            f'🔗 <b>Username:</b> {seller_username}',
            f'📞 <b>Phone:</b> {phone}',
            '',
            f'🕒 <b>Posted:</b> {posted_when}',
        ]
        
        # Add release info if it's a repost
        total_releases = plate_info.get('total_releases', 1) if plate_info else 1
        last_seen = plate_info.get('last_seen_at') if plate_info else None
        if not is_new_plate and plate_info:
            lines.extend([
                '',
                f'🔁 <b>Total Releases Seen:</b> {total_releases}',
            ])
            if last_seen:
                lines.append(f'⏰ <b>Last Seen:</b> {last_seen}')
        
        lines.extend([
            '',
            '✅ <b>Reason:</b> Sent because this listing matched your saved alert rule.',
            '',
            f'🔗 <a href="{listing_link}">Open Listing</a>',
        ])
    return '\n'.join(lines)


def _get_interval_seconds(alert: dict[str, Any]) -> int:
    if alert.get('monitoring_interval_seconds') is not None:
        try:
            seconds = int(alert.get('monitoring_interval_seconds') or 0)
            return min(max(seconds, 10), 3600)
        except Exception:
            pass
    if alert.get('check_interval_seconds') is not None:
        try:
            seconds = int(alert.get('check_interval_seconds') or 0)
            return min(max(seconds, 10), 3600)
        except Exception:
            pass
    if alert.get('check_interval_minutes') is not None:
        try:
            minutes = int(alert.get('check_interval_minutes') or 0)
            return max(minutes * 60, 20)
        except Exception:
            pass
    return 20 if alert.get('immediate_alerts_mode', True) else 60


def _get_seen_keys(alert: Alert) -> set[str]:
    seen = set(alert.seen_listing_keys or [])
    seen.update(f"id:{value}" for value in (alert.seen_listing_ids or []) if value)
    seen.update(f"url:{value}" for value in (alert.seen_listing_urls or []) if value)
    return seen


def _get_sent_keys(alert: Alert) -> set[str]:
    return set(getattr(alert, 'sent_listing_keys', []) or [])


def clear_scheduler_cache() -> None:
    RUNNING_ALERTS.clear()
    DISABLED_SKIP_LOGGED.clear()


def request_stop_all(disabled_count: int) -> None:
    global STOP_ALL_ALERTS_ACTIVE, STOP_ALL_REQUESTED_AT
    STOP_ALL_ALERTS_ACTIVE = True
    STOP_ALL_REQUESTED_AT = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    clear_scheduler_cache()
    print(f"STOP ALL ALERTS: disabled {disabled_count} alerts and cleared scheduler cache")


def clear_stop_all() -> None:
    global STOP_ALL_ALERTS_ACTIVE
    STOP_ALL_ALERTS_ACTIVE = False


def stop_all_active() -> bool:
    return STOP_ALL_ALERTS_ACTIVE


def scheduler_running() -> bool:
    return bool(SCHEDULER and SCHEDULER.running)


def active_alert_ids() -> list[str]:
    return [str(alert_id) for alert_id, running in RUNNING_ALERTS.items() if running]


def _storage_alert_enabled(alert_id: str) -> bool:
    alerts = get_alerts()
    if not alerts:
        return False
    current = next((item for item in alerts if str(item.get('id') or '') == str(alert_id or '')), None)
    return bool(current and _is_enabled_value(current.get('enabled')))


def _storage_alert(alert_id: str) -> dict[str, Any] | None:
    return next((item for item in get_alerts() if str(item.get('id') or '') == str(alert_id or '')), None)


def _listing_already_sent(alert_data: dict[str, Any], listing: dict[str, Any]) -> bool:
    sent = set(alert_data.get('sent_listing_keys') or [])
    sent.update(alert_data.get('notified_listing_keys') or [])
    key = _listing_key(listing)
    url = _listing_url(listing)
    listing_id = _extract_listing_id(listing)
    return (
        bool(key and key in sent)
        or bool(url and f"url:{url}" in sent)
        or bool(listing_id is not None and f"id:{listing_id}" in sent)
    )


def _trim_alert_model(alert: Alert) -> Alert:
    return Alert(**trim_alert_runtime_state(alert.model_dump()))


def _mark_listing_key(target: set[str], row: dict[str, Any]) -> None:
    key = _listing_key(row)
    if key:
        target.add(key)
    listing_url = _listing_url(row)
    if listing_url:
        target.add(f"url:{listing_url}")
    listing_id = _extract_listing_id(row)
    if listing_id is not None:
        target.add(f"id:{listing_id}")


def _derive_max_seen_listing_id(alert: Alert) -> int:
    values: list[int] = []
    for value in alert.seen_listing_ids or []:
        text = str(value or '').strip()
        if text.isdigit():
            values.append(int(text))
    for key in alert.seen_listing_keys or []:
        match = re.match(r"id:(\d+)$", str(key or '').strip())
        if match:
            values.append(int(match.group(1)))
    for url in alert.seen_listing_urls or []:
        match = re.search(r"/license-plates/(\d+)(?:[-/]|$)", str(url or ''))
        if match:
            values.append(int(match.group(1)))
    return max(values) if values else 0


def _search_rows(alert: Alert) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    collect_details = bool(alert.enrich_listing_details) or not bool(alert.fast_alert_mode)
    max_listings = _auto_max_listings_per_scan(alert)
    max_pages = _auto_max_pages_per_scan(alert)
    fresh_window = _auto_fresh_listing_window(alert)
    search_depth = "All pages"
    alert_cities = [_city_to_scraper_value(city) for city in _alert_cities(alert)]
    if alert.send_all_new_plates:
        if stop_all_active() or (alert.id and not _storage_alert_enabled(str(alert.id))):
            print(f"Alert search stopped before scan: id={alert.id or '(missing)'}")
            return []
        for city in alert_cities or [""]:
            _log_scraper_city(alert, city)
        return search_xplate(
            number=alert.plate_number,
            search_mode=alert.search_mode if alert.plate_number else 'contains',
            code=alert.code,
            contains=alert.contains,
            starts_with=alert.starts_with,
            ends_with=alert.ends_with,
            min_price='',
            max_price=alert.price_max,
            cities=alert_cities,
            number_format=alert.number_format,
            number_formats=alert.number_formats,
            search_depth=search_depth,
            collect_details=collect_details,
            detail_timeout=5,
            max_listings=max_listings,
            max_pages_override=max_pages,
            auto_recent_window_minutes=fresh_window,
        )

    cities = alert_cities or [""]
    if any(c.lower() in {'all', 'all cities'} for c in cities):
        cities = [""]

    for city in cities:
        if stop_all_active() or (alert.id and not _storage_alert_enabled(str(alert.id))):
            print(f"Alert search stopped before city scan: id={alert.id or '(missing)'} city={city or 'All cities'}")
            break
        _log_scraper_city(alert, city)
        page_rows = search_xplate(
            number=alert.plate_number,
            search_mode=alert.search_mode,
            code=alert.code,
            contains=alert.contains,
            starts_with=alert.starts_with,
            ends_with=alert.ends_with,
            min_price=alert.price_min,
            max_price=alert.price_max,
            cities=[city] if city else [],
            number_format=alert.number_format,
            number_formats=alert.number_formats,
            search_depth=search_depth,
            collect_details=collect_details,
            detail_timeout=5,
            max_listings=max_listings,
            max_pages_override=max_pages,
            auto_recent_window_minutes=fresh_window,
        )
        req = SearchRequest(
            plate_number=alert.plate_number,
            search_mode=alert.search_mode,
            cities=alert.cities,
            city=city,
            code=alert.code,
            price_min=alert.price_min,
            price_max=alert.price_max,
            contains=alert.contains,
            starts_with=alert.starts_with,
            ends_with=alert.ends_with,
            number_format=alert.number_format,
            number_formats=alert.number_formats,
            search_depth='First page only',
            sort='Newest first',
            hide_duplicates=True,
        )
        filtered = apply_filters(page_rows, req)
        rows.extend(filtered)

    return rows


def initialize_baseline(alert_dict: dict[str, Any]) -> dict[str, Any]:
    alert_dict = _ensure_alert_city_fields(alert_dict)
    alert = Alert(**alert_dict)
    alert.number_formats = normalize_number_formats(alert.number_formats, fallback=alert.number_format)
    alert.number_format = number_format_label(alert.number_formats[0]) if alert.number_formats else 'Any format'
    now = datetime.utcnow()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    alert.enabled_at = now_str
    alert.activated_at = now_str
    alert.baseline_created_at = now_str
    alert.baseline_completed = False
    existing_sent_keys = set(getattr(alert, 'sent_listing_keys', []) or [])
    alert.seen_listing_keys = []
    alert.seen_listing_ids = []
    alert.seen_listing_urls = []
    alert.notified_listing_keys = list(existing_sent_keys)

    rows = [row for row in _search_rows(alert) if _city_filter_decision(alert, row)[0]]
    keys = {key for row in rows if (key := _listing_key(row))}
    urls = {url for row in rows if (url := _listing_url(row))}
    numeric_ids = {_extract_listing_id(row) for row in rows}
    numeric_ids = {listing_id for listing_id in numeric_ids if listing_id is not None}
    ids = {str(listing_id) for listing_id in numeric_ids}
    max_seen_listing_id = max(numeric_ids) if numeric_ids else 0
    alert.seen_listing_keys = list(keys)
    alert.seen_listing_ids = list(ids)
    alert.seen_listing_urls = list(urls)
    alert.notified_listing_keys = list(existing_sent_keys)
    alert.sent_listing_keys = list(existing_sent_keys)
    alert.max_seen_listing_id = max_seen_listing_id
    alert.baseline_completed = True
    alert.baseline_created = True
    alert.last_checked_at = now_str
    alert.last_scan_at = now_str
    alert.last_match_count = len(rows)
    alert.last_status = 'baseline_completed'
    alert.updated_at = now_str
    alert = _trim_alert_model(alert)

    save_alert(alert.model_dump())
    log = AlertLog(
        id=str(uuid.uuid4()),
        alert_id=alert.id,
        alert_name=alert.name,
        checked_at=alert.last_checked_at,
        status='baseline_completed',
        event_type='Skipped',
        severity='warning',
        message=f'Baseline created with {len(keys)} listings. Max baseline listing ID: {max_seen_listing_id}. Future listings only.',
        matches_count=len(rows),
        sent_notifications=0,
        error='',
        reason='Reset baseline from now saved current listings as already seen.',
        details=[
            *_alert_identity_lines(alert),
            f'Alert name: {alert.name or alert.id}',
            f'activated_at: {alert.activated_at}',
            f'baseline_created_at: {alert.baseline_created_at}',
            'Baseline scan started',
            f'Baseline created: yes',
            f'Number of listings saved to baseline: {len(keys)}',
            f'Baseline created with {len(keys)} listings',
            f'Max baseline listing ID: {max_seen_listing_id}',
            'Listing skipped because first scan is baseline-only.',
            'No Telegram messages sent for baseline listings.',
            'Only future listings will be sent.',
        ]
    )
    add_alert_log(log.model_dump())
    return alert.model_dump()


def check_alert(alert_dict: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    global LAST_ERROR
    alert_dict = _ensure_alert_city_fields(alert_dict)
    alert = Alert(**alert_dict)
    alert.number_formats = normalize_number_formats(alert.number_formats, fallback=alert.number_format)
    alert.number_format = number_format_label(alert.number_formats[0]) if alert.number_formats else 'Any format'
    alert_id = alert.id or str(uuid.uuid4())
    if alert.baseline_created and alert.baseline_completed and not alert.max_seen_listing_id:
        alert.max_seen_listing_id = _derive_max_seen_listing_id(alert)
        alert_dict['max_seen_listing_id'] = alert.max_seen_listing_id
        if dry_run or _storage_alert_enabled(str(alert_id)):
            save_alert(alert.model_dump())
    now = datetime.utcnow()
    matches: list[dict[str, Any]] = []
    try:
        if not dry_run and (stop_all_active() or not _storage_alert_enabled(str(alert.id or ''))):
            checked_at = now.strftime('%Y-%m-%d %H:%M:%S')
            reason = 'Emergency stop-all is active.' if stop_all_active() else 'Alert is disabled or missing in storage.'
            add_alert_log(AlertLog(
                id=str(uuid.uuid4()),
                alert_id=alert_id,
                alert_name=alert.name,
                checked_at=checked_at,
                status='stopped',
                event_type='Skipped',
                severity='warning',
                message=f"Stopped alert rule before scan: {_alert_display_name(alert)}. No Telegram send.",
                matches_count=0,
                sent_notifications=0,
                error='',
                listing={},
                reason=reason,
                details=[
                    *_alert_identity_lines(alert),
                    reason,
                    'No scan performed.',
                    'No Telegram messages sent.',
                ],
            ).model_dump())
            return {
                'ok': True,
                'total_scraped': 0,
                'scraped': 0,
                'matched': 0,
                'new_after_baseline': 0,
                'skipped_baseline': 0,
                'eligible_to_send': 0,
                'sent': 0,
                'failed': 0,
                'skipped_old': 0,
                'skipped_featured': 0,
                'skipped_city_mismatch': 0,
                'skipped_duplicate': 0,
                'telegram_ready': False,
                'telegram_attempts': 0,
                'message': f'Stopped: {reason}',
            }
        if not alert.enabled:
            checked_at = now.strftime('%Y-%m-%d %H:%M:%S')
            add_alert_log(AlertLog(
                id=str(uuid.uuid4()),
                alert_id=alert_id,
                alert_name=alert.name,
                checked_at=checked_at,
                status='disabled',
                event_type='Skipped',
                severity='warning',
                message=f"Skipped disabled alert rule: {_alert_display_name(alert)}. No scan and no Telegram send.",
                matches_count=0,
                sent_notifications=0,
                error='',
                listing={},
                reason='Alert is disabled.',
                details=[
                    *_alert_identity_lines(alert),
                    'Skipped disabled alert before scraping.',
                    'No scan performed.',
                    'No Telegram messages sent.',
                ],
            ).model_dump())
            return {
                'ok': True,
                'total_scraped': 0,
                'scraped': 0,
                'matched': 0,
                'new_after_baseline': 0,
                'skipped_baseline': 0,
                'eligible_to_send': 0,
                'sent': 0,
                'failed': 0,
                'skipped_old': 0,
                'skipped_featured': 0,
                'skipped_duplicate': 0,
                'skipped_price': 0,
                'telegram_attempts': 0,
                'errors': [],
                'message': f"Rule {_alert_display_name(alert)} is disabled. Nothing was scanned or sent.",
            }
        if alert.enabled and not (alert.baseline_created and alert.baseline_completed):
            baseline = initialize_baseline(alert.model_dump())
            baseline_count = int(baseline.get('last_match_count') or 0)
            return {
                'ok': True,
                'total_scraped': baseline_count,
                'scraped': baseline_count,
                'matched': baseline_count,
                'new_after_baseline': 0,
                'skipped_baseline': baseline_count,
                'eligible_to_send': 0,
                'sent': 0,
                'failed': 0,
                'skipped_old': baseline_count,
                'skipped_duplicate': 0,
                'skipped_price': 0,
                'telegram_ready': bool(_resolve_telegram_credentials(alert)[0] and _resolve_telegram_credentials(alert)[1]),
                'telegram_attempts': 0,
                'telegram_token_found': bool(_resolve_telegram_credentials(alert)[0]),
                'telegram_channel_found': bool(_resolve_telegram_credentials(alert)[1]),
                'errors': [],
                'message': f"Baseline created for alert {alert.name or alert.id}. Saved {baseline_count} current listings. Future listings only.",
            }

        matches = _search_rows(alert)
        if not dry_run and (stop_all_active() or not _storage_alert_enabled(str(alert.id or ''))):
            checked_at = now.strftime('%Y-%m-%d %H:%M:%S')
            reason = 'Emergency stop-all became active during scan.' if stop_all_active() else 'Alert was disabled or removed during scan.'
            add_alert_log(AlertLog(
                id=str(uuid.uuid4()),
                alert_id=alert_id,
                alert_name=alert.name,
                checked_at=checked_at,
                status='stopped',
                event_type='Skipped',
                severity='warning',
                message=f"Stopped alert rule after scraping and before filtering/sending: {_alert_display_name(alert)}.",
                matches_count=0,
                sent_notifications=0,
                error='',
                listing={},
                reason=reason,
                details=[
                    *_alert_identity_lines(alert),
                    reason,
                    f"Listings discarded before send: {len(matches)}",
                    'No Telegram messages sent.',
                ],
            ).model_dump())
            print(f"Scan stopped before send: alert_id={alert.id or '(missing)'} reason={reason}")
            matches.clear()
            return {
                'ok': True,
                'total_scraped': 0,
                'scraped': 0,
                'matched': 0,
                'new_after_baseline': 0,
                'skipped_baseline': 0,
                'eligible_to_send': 0,
                'sent': 0,
                'failed': 0,
                'skipped_old': 0,
                'skipped_featured': 0,
                'skipped_city_mismatch': 0,
                'skipped_duplicate': 0,
                'telegram_ready': False,
                'telegram_attempts': 0,
                'message': f'Stopped: {reason}',
            }
        fresh_window = _auto_fresh_listing_window(alert)
        auto_max_pages = _auto_max_pages_per_scan(alert)
        row_logs: list[str] = []
        row_logs.append('Scan started')
        row_logs.extend(_alert_identity_lines(alert))
        row_logs.append(f'Alert name: {alert.name or alert.id}')
        row_logs.append(f'activated_at: {alert.activated_at or alert.enabled_at or "(missing)"}')
        row_logs.append(f'Raw listings found: {len(matches)}')
        page_counts: dict[str, int] = {}
        for row in matches:
            source_url = str(row.get('source_url') or '')
            page = (parse_qs(urlparse(source_url).query).get('page') or ['1'])[0]
            page_counts[page] = page_counts.get(page, 0) + 1
        for page in sorted(page_counts, key=lambda value: int(value) if str(value).isdigit() else 0):
            row_logs.append(f"Listings found page={page}: {page_counts[page]}")
        row_logs.extend([
            f"enabled: {'yes' if alert.enabled else 'no'}",
            f"baseline_created: {'yes' if alert.baseline_created and alert.baseline_completed else 'no'}",
            f"baseline_time: {alert.baseline_created_at or '(missing)'}",
            f"max_seen_listing_id: {alert.max_seen_listing_id or 0}",
            f"pages_scanned: auto up to {auto_max_pages}",
            f"unique_listings_total: {len({(_listing_url(row) or _listing_key(row)) for row in matches})}",
            'Checking baseline and duplicate protection',
        ])
        if not (bool(alert.enrich_listing_details) or not bool(alert.fast_alert_mode)):
            row_logs.append('Detail enrichment OFF: using listing-card data only')
        else:
            row_logs.append('Collecting seller details with 5 second timeout per listing')
        if alert.send_all_new_plates:
            row_logs.extend([
                'Send All New Plates is enabled',
                'Automatic fresh listing detection is enabled; city, code, price, number format, and text filters are enforced',
            ])

        # De-duplicate listings by listing link before alert matching
        seen_links = set()
        unique_matches: list[dict[str, Any]] = []
        for row in matches:
            link = str(row.get('listing_link') or '').strip()
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)
            unique_matches.append(row)

        final_matches: list[dict[str, Any]] = []
        price_rejects = 0
        sold_rejects = 0
        featured_rejects = 0
        format_rejects = 0
        city_mismatch_rejects = 0
        city_missing_rejects = 0
        matched_city_count = 0
        alert_city_filters = _alert_city_filters(alert)
        alert_city_log = ', '.join(alert_city_filters) if alert_city_filters else 'All cities'
        max_price_value = None
        if alert.alert_only_price_below and alert.price_max:
            try:
                max_price_value = float(alert.price_max)
            except Exception:
                max_price_value = None

        for row in unique_matches:
            city_matched, city_skip_reason, alert_city_text, listing_city_text = _city_filter_decision(alert, row)
            if not city_matched:
                if city_skip_reason == 'City missing for city-specific alert':
                    city_missing_rejects += 1
                else:
                    city_mismatch_rejects += 1
                row_logs.extend([
                    f"listing: {row.get('city') or '?'} {row.get('code') or '?'} {row.get('plate_number') or '?'}",
                    f"listing_city: {row.get('city') or '?'}",
                    f"alert_city: {alert_city_text or 'All cities'}",
                    f"normalized_listing_city: {listing_city_text or '?'}",
                    f"normalized_alert_city: {alert_city_text or 'All cities'}",
                    "city_matched: no",
                    "would_send: no",
                    f"skip_reason: {city_skip_reason}",
                ])
                continue
            matched_city_count += 1
            if max_price_value is not None:
                price_num = price_to_number(row.get('price', ''))
                if price_num is None or price_num > max_price_value:
                    price_rejects += 1
                    continue
            format_decision = _format_match_decision(alert, row)
            if not format_decision.get('matched'):
                format_rejects += 1
                row_logs.extend([
                    f"listing: {row.get('city') or '?'} {row.get('code') or '?'} {row.get('plate_number') or '?'}",
                    f"selected_formats: {', '.join(format_decision.get('selected_format_labels') or [])}",
                    "format_matched: no",
                    f"skip_reason: {format_decision.get('skip_reason') or 'number format mismatch'}",
                ])
                continue
            final_matches.append(row)

        baseline_seen = _get_seen_keys(alert)
        sent_keys = _get_sent_keys(alert)
        max_seen_listing_id = int(alert.max_seen_listing_id or 0)
        to_notify: list[tuple[str, dict[str, Any]]] = []
        old_rejects = 0
        date_rejects = 0
        already_notified_rejects = 0
        last_checked_dt = None
        enabled_at_dt = None
        if alert.alert_only_new and alert.last_checked_at:
            try:
                last_checked_dt = datetime.strptime(alert.last_checked_at, '%Y-%m-%d %H:%M:%S')
            except Exception:
                last_checked_dt = None
        activation_text = alert.activated_at or alert.enabled_at
        if activation_text:
            try:
                enabled_at_dt = datetime.strptime(activation_text, '%Y-%m-%d %H:%M:%S')
            except Exception:
                enabled_at_dt = None

        for row in final_matches:
            key = _listing_key(row)
            listing_url = _listing_url(row)
            numeric_listing_id = _extract_listing_id(row)
            listing_id = str(numeric_listing_id) if numeric_listing_id is not None else ''
            plate_text = f"{row.get('plate_number','?')}".strip()
            city_text = f"{row.get('city','?')}".strip()
            sent_before = key in sent_keys or (listing_url and f"url:{listing_url}" in sent_keys) or (numeric_listing_id is not None and f"id:{numeric_listing_id}" in sent_keys)
            baseline_seen_before = key in baseline_seen or (listing_url and f"url:{listing_url}" in baseline_seen) or (numeric_listing_id is not None and f"id:{numeric_listing_id}" in baseline_seen)
            id_newer_than_baseline = numeric_listing_id is not None and numeric_listing_id > max_seen_listing_id
            posted_text = _posted_when(row)
            recent_posted = is_recent_posted_text(posted_text, fresh_window)
            city_matched, city_skip_reason, alert_city_text, listing_city_text = _city_filter_decision(alert, row)
            format_decision = _format_match_decision(alert, row)
            would_send = False
            skip_reason = ''
            posted_missing = posted_text in {'', '?', 'Not available', 'Not collected in fast mode'}
            decision_log = [
                f"alert_id: {alert.id or '(missing)'}",
                f"alert_name: {alert.name or alert.id}",
                f"alert_city: {alert_city_text or 'All cities'}",
                f"enabled: {'yes' if alert.enabled else 'no'}",
                f"listing_id: {listing_id or '(missing)'}",
                f"listing_url: {listing_url or '(missing)'}",
                f"plate: {row.get('plate_number') or '?'}",
                f"selected_formats: {', '.join(format_decision.get('selected_format_labels') or []) or 'Any format'}",
                f"format_matched: {'yes' if format_decision.get('matched') else 'no'}",
                f"matched_format_name: {format_decision.get('matched_format_name') or '(none)'}",
                f"city: {row.get('city') or '?'}",
                f"listing_city: {row.get('city') or '?'}",
                f"city_matched: {'yes' if city_matched else 'no'}",
                f"code: {row.get('code') or '?'}",
                f"price: {row.get('price') or '?'}",
                f"posted_text: {posted_text}",
                f"phone_found: {'yes' if str(row.get('phone_number') or '').strip() not in {'', '?', 'Not available'} else 'no'}",
                f"posted_time_found: {'yes' if _posted_when(row) != '?' else 'no'}",
                f"featured: {'yes' if row.get('featured') else 'no'}",
                f"include_featured: {bool(alert.include_featured_listings)}",
                f"sold: {'yes' if row.get('sold') else 'no'}",
                f"include_sold: {bool(alert.include_sold_listings)}",
                f"listing_type: {row.get('listing_type') or 'unknown'}",
                f"baseline_created: {bool(alert.baseline_created and alert.baseline_completed)}",
                f"max_seen_listing_id: {max_seen_listing_id}",
                f"already_sent: {sent_before}",
                f"baseline_seen: {baseline_seen_before}",
                f"listing_id_newer_than_baseline: {id_newer_than_baseline}",
                f"recent: {'yes' if recent_posted else 'no'}",
            ]
            if sent_before:
                already_notified_rejects += 1
                skip_reason = 'already sent'
                row_logs.extend([*decision_log, "matched_filters: yes", "telegram_sent: no", "will_send: False", f"skip_reason: {skip_reason}"])
                row_logs.append(f"Listing skipped because already sent | Plate: {city_text} {plate_text} | Key: {key}")
                continue
            if bool(row.get('sold')) and not bool(alert.include_sold_listings):
                sold_rejects += 1
                skip_reason = 'Skipped sold listing because Include sold listings is OFF.'
                row_logs.extend([*decision_log, "matched_filters: yes", "telegram_sent: no", "will_send: False", f"skip_reason: {skip_reason}"])
                row_logs.append(skip_reason)
                continue
            if bool(row.get('featured')) and not bool(alert.include_featured_listings):
                featured_rejects += 1
                skip_reason = 'Skipped featured listing because Include featured listings is OFF.'
                row_logs.extend([*decision_log, "matched_filters: yes", "telegram_sent: no", "will_send: False", f"skip_reason: {skip_reason}"])
                row_logs.append(skip_reason)
                continue

            if recent_posted:
                would_send = True
                skip_reason = ''
            elif baseline_seen_before:
                skip_reason = 'Skipped old baseline listing because posted text is not recent.'
            elif posted_missing and numeric_listing_id is not None and numeric_listing_id > max_seen_listing_id and not (row.get('featured') or row.get('sold')):
                would_send = True
                skip_reason = ''
            elif posted_missing and numeric_listing_id is not None and numeric_listing_id > max_seen_listing_id:
                skip_reason = 'Skipped static featured/sold listing: ID is newer than baseline but posted text is missing.'
            elif numeric_listing_id is not None and numeric_listing_id <= max_seen_listing_id and posted_missing:
                skip_reason = 'Skipped old/static listing: no recent posted time and ID is not newer than baseline.'
            else:
                skip_reason = 'Skipped old listing because posted text is outside the fresh window.'

            if not would_send:
                old_rejects += 1
                _mark_listing_key(baseline_seen, row)
                row_logs.extend([*decision_log, "matches_alert_filters: yes", "will_send: False", "send_decision: skip", f"skip_reason: {skip_reason}"])
                row_logs.append(skip_reason)
                continue

            to_notify.append((key, row))
            row_logs.extend([*decision_log, "matched_filters: yes", "telegram_sent: pending", "will_send: True", "send_decision: send", "skip_reason: none"])
            row_logs.append(f"Queued listing ID {listing_id or '(missing)'} because {'posted text is recent' if recent_posted else 'listing ID is newer than baseline'}")

        row_logs.append(f'New listings after baseline: {len(to_notify)}')
        recent_count = sum(1 for row in final_matches if is_recent_posted_text(_posted_when(row), fresh_window))
        row_logs.extend([
            f"Alert: {alert.name or alert.id}",
            f"Alert ID: {alert.id or '(missing)'}",
            f"Alert name: {_alert_display_name(alert)}",
            f"Alert city: {alert_city_log}",
            f"Enabled: {'yes' if alert.enabled else 'no'}",
            f"Pages scanned: automatic, up to {auto_max_pages}",
            f"Cards found: {len(matches)}",
            f"Unique listings: {len(unique_matches)}",
            f"Total listings found: {len(matches)}",
            f"Matched city: {matched_city_count}",
            f"Skipped city mismatch: {city_mismatch_rejects}",
            f"Skipped city missing: {city_missing_rejects}",
            f"Recent listings: {recent_count}",
            f"Matched filters: {len(final_matches)}",
            f"Skipped format mismatch: {format_rejects}",
            f"Already sent: {already_notified_rejects}",
            f"Skipped featured: {featured_rejects}",
            f"Skipped sold: {sold_rejects}",
            f"Skipped old: {old_rejects + date_rejects}",
            f"Sent: pending {len(to_notify)}",
        ])

        sent = 0
        telegram_failed = 0
        errors: list[str] = []
        bot_token, chat_id = _resolve_telegram_credentials(alert)
        telegram_ready = bool(bot_token and chat_id)
        if to_notify and not bot_token:
            errors.append('Telegram bot token missing')
        if to_notify and not chat_id:
            errors.append('Telegram channel ID missing')

        # Get configuration for duplicate checking
        config = get_config()
        send_logs: list[str] = []
        duplicate_send_skips = 0
        telegram_attempts = 0
        final_city_guard_skips = 0

        row_logs.extend([
            'Alert decision started',
            f"Alert ID: {alert.id or '(missing)'}",
            f"Alert name: {_alert_display_name(alert)}",
            f"Rule mode: {'Send all new plates' if alert.send_all_new_plates else 'Specific matching alert'}",
            f"Alert city: {alert_city_log}",
            f"Enabled: {'yes' if alert.enabled else 'no'}",
            f'Total scraped: {len(matches)}',
            f"Total listing links found: {len(matches)}",
            f"Total unique listing IDs: {len({str(_extract_listing_id(row)) for row in unique_matches if _extract_listing_id(row) is not None})}",
            f"Featured listings found: {sum(1 for row in unique_matches if row.get('featured'))}",
            f"Sold listings found: {sum(1 for row in unique_matches if row.get('sold'))}",
            f"Listings with phone found: {sum(1 for row in unique_matches if str(row.get('phone_number') or '').strip() not in {'', '?', 'Not available'})}",
            f"Listings with posted time found: {sum(1 for row in unique_matches if _posted_when(row) != '?')}",
            f"Recent listings found: {sum(1 for row in final_matches if is_recent_posted_text(_posted_when(row), fresh_window))}",
            f"Listings matched city: {matched_city_count}",
            f"Listings skipped city mismatch: {city_mismatch_rejects}",
            f"Listings skipped city missing: {city_missing_rejects}",
            f"Listings skipped because sold: {sold_rejects}",
            f"Listings skipped because featured/promoted: {featured_rejects}",
            f"Listings skipped because number format mismatch: {format_rejects}",
            f'Matched by rule: {len(final_matches)}',
            f'New after baseline: {len(to_notify)}',
            f'Skipped because already sent: {already_notified_rejects}',
            f'Skipped because duplicate: {duplicate_send_skips}',
            f'Skipped because posted before alert enabled time: {date_rejects}',
            f'Skipped because older than last scan: {old_rejects}',
        ])
        
        if dry_run:
            debug_listings = []
            for row in unique_matches:
                numeric_listing_id = _extract_listing_id(row)
                key = _listing_key(row)
                listing_url = _listing_url(row)
                sent_before = key in sent_keys or (listing_url and f"url:{listing_url}" in sent_keys) or (numeric_listing_id is not None and f"id:{numeric_listing_id}" in sent_keys)
                baseline_seen_before = key in baseline_seen or (listing_url and f"url:{listing_url}" in baseline_seen) or (numeric_listing_id is not None and f"id:{numeric_listing_id}" in baseline_seen)
                posted_text = _posted_when(row)
                recent_posted = is_recent_posted_text(posted_text, fresh_window)
                id_newer = numeric_listing_id is not None and numeric_listing_id > max_seen_listing_id
                city_matched, city_skip_reason, alert_city_text, listing_city_text = _city_filter_decision(alert, row)
                format_decision = _format_match_decision(alert, row)
                matched = row in final_matches
                featured_blocked = bool(row.get('featured')) and not bool(alert.include_featured_listings)
                sold_blocked = bool(row.get('sold')) and not bool(alert.include_sold_listings)
                posted_missing = posted_text in {'', '?', 'Not available', 'Not collected in fast mode'}
                would_send = city_matched and matched and not sent_before and not featured_blocked and not sold_blocked and (
                    recent_posted or (posted_missing and id_newer and not baseline_seen_before)
                )
                reason = (
                    'would send' if would_send else
                    city_skip_reason if not city_matched else
                    (format_decision.get('skip_reason') or 'number format mismatch') if not format_decision.get('matched') else
                    'filter mismatch' if not matched else
                    'already sent' if sent_before else
                    'featured disabled' if featured_blocked else
                    'sold disabled' if sold_blocked else
                    'old baseline' if baseline_seen_before and not recent_posted else
                    'old listing'
                )
                debug_listings.append({
                    'listing_id': str(numeric_listing_id or ''),
                    'url': listing_url,
                    'page_number': (parse_qs(urlparse(str(row.get('source_url') or '')).query).get('page') or ['1'])[0],
                    'plate': f"{row.get('city') or '?'} {row.get('code') or '?'} {row.get('plate_number') or '?'}",
                    'listing_city': row.get('city') or '?',
                    'alert_city': alert_city_text or 'All cities',
                    'normalized_listing_city': listing_city_text or '?',
                    'normalized_alert_city': alert_city_text or 'All cities',
                    'city_matched': bool(city_matched),
                    'city_matched_text': 'yes' if city_matched else 'no',
                    'price': row.get('price') or '?',
                    'phone': _format_phone(row.get('phone_number')),
                    'posted_text': posted_text,
                    'featured': bool(row.get('featured')),
                    'sold': bool(row.get('sold')),
                    'matched': matched,
                    'listing_number': row.get('plate_number') or '?',
                    'selected_formats': format_decision.get('selected_format_labels') or [],
                    'format_matched': bool(format_decision.get('matched')),
                    'format_matched_text': 'yes' if format_decision.get('matched') else 'no',
                    'matched_format_name': format_decision.get('matched_format_name') or '',
                    'already_sent': bool(sent_before),
                    'already_seen': bool(baseline_seen_before),
                    'recent': bool(recent_posted),
                    'would_send': would_send,
                    'would_send_text': 'yes' if would_send else 'no',
                    'skip_reason': reason,
                })
            return {
                'ok': True,
                'dry_run': True,
                'total_scraped': len(matches),
                'pages_scanned': auto_max_pages,
                'matched': len(final_matches),
                'new_after_baseline': len(to_notify),
                'skipped_old': old_rejects + date_rejects,
                'skipped_featured': featured_rejects,
                'skipped_city_mismatch': city_mismatch_rejects,
                'skipped_city_missing': city_missing_rejects,
                'matched_city': matched_city_count,
                'skipped_filters': max(len(unique_matches) - len(final_matches), 0),
                'sent': 0,
                'debug_listings': debug_listings,
                'decision_logs': row_logs,
                'message': f"Debug scan completed: {len(matches)} found, {len(final_matches)} matched, {len(to_notify)} would send.",
        }

        for key, row in to_notify:
            if stop_all_active() or not _storage_alert_enabled(str(alert.id or '')):
                row_logs.append('Telegram send aborted: emergency stop-all active, or alert is disabled/missing in storage.')
                send_logs.append('Telegram send aborted before API request.')
                break
            city_matched, city_skip_reason, normalized_alert_city, normalized_listing_city = _city_filter_decision(alert, row)
            format_decision = _format_match_decision(alert, row)
            send_header_lines = [
                f"Sending Telegram for alert: {_alert_display_name(alert)}",
                f"Alert ID: {alert.id or '(missing)'}",
                f"Alert name: {_alert_display_name(alert)}",
                f"Alert city: {_alert_city_log_value(alert)}",
                f"Listing city: {row.get('city') or '?'}",
            ]
            row_logs.extend(send_header_lines)
            send_logs.extend(send_header_lines)
            send_decision_lines = _city_send_decision_lines(alert, row, city_matched, city_skip_reason)
            row_logs.extend(send_decision_lines)
            send_logs.extend(send_decision_lines)
            if not city_matched:
                final_city_guard_skips += 1
                if city_skip_reason == 'City missing for city-specific alert':
                    city_missing_rejects += 1
                else:
                    city_mismatch_rejects += 1
                row_logs.append(f"Final send guard skipped {row.get('city') or '?'} {row.get('code') or '?'} {row.get('plate_number') or '?'}: {city_skip_reason}")
                send_logs.append(f"Telegram not sent: {city_skip_reason}")
                continue

            if not format_decision.get('matched'):
                final_city_guard_skips += 1
                format_rejects += 1
                skip_reason = format_decision.get('skip_reason') or 'number format mismatch'
                row_logs.append(f"Telegram not sent for {row.get('plate_number') or '?'}: {skip_reason}")
                send_logs.append(f"Telegram not sent: {skip_reason}")
                continue

            if errors:
                telegram_failed += 1
                send_logs.append(f"Send skipped for {row.get('plate_number','?')} due to credential error")
                continue
            
            try:
                # Extract plate info
                city = str(row.get('city', '')).strip()
                code = str(row.get('code', '')).strip()
                plate_number = str(row.get('plate_number', '')).strip()
                price = str(row.get('price', '')).strip()
                seller_name = str(row.get('seller_name', '')).strip()
                seller_username = str(row.get('seller_username', '')).strip()
                listing_link = str(row.get('listing_link', '')).strip()

                telegram_attempts += 1
                row_logs.append(f"Sending Telegram for {plate_number}")
                send_logs.append(f"Telegram send attempted for {plate_number}")
                if stop_all_active() or not _storage_alert_enabled(str(alert.id or '')):
                    row_logs.append('Telegram send cancelled immediately before API request.')
                    send_logs.append('Telegram send cancelled immediately before API request.')
                    break
                send_result = send_telegram_plate_alert(bot_token, chat_id, alert, row)
                if send_result.get('skipped'):
                    skip_reason = send_result.get('skip_reason') or 'City mismatch'
                    if 'duplicate' in skip_reason.lower() or 'already sent' in skip_reason.lower():
                        duplicate_send_skips += 1
                    else:
                        final_city_guard_skips += 1
                        if skip_reason == 'City missing for city-specific alert':
                            city_missing_rejects += 1
                        elif 'format' in skip_reason.lower():
                            format_rejects += 1
                        else:
                            city_mismatch_rejects += 1
                    guard_lines = _city_send_decision_lines(alert, row, False, skip_reason)
                    row_logs.extend(guard_lines)
                    send_logs.extend(guard_lines)
                    row_logs.append(f"Telegram sender refused {city or '?'} {code or '?'} {plate_number or '?'}: {skip_reason}")
                    send_logs.append(f"Telegram not sent: {skip_reason}")
                    continue

                # Track only after the city-safe Telegram sender has accepted the listing.
                plate_info = plate_tracking.track_plate(
                    city, code, plate_number, price, seller_name, seller_username, listing_link
                )
                
                # Mark as sent in tracking database
                plate_tracking.mark_telegram_sent(city, code, plate_number, alert.id)
                
                _mark_listing_key(sent_keys, row)
                _mark_listing_key(baseline_seen, row)
                sent += 1
                release_count = plate_info.get('total_releases', 1) if plate_info else 1
                numeric_listing_id = _extract_listing_id(row)
                if numeric_listing_id is not None:
                    max_seen_listing_id = max(max_seen_listing_id, numeric_listing_id)
                    alert.max_seen_listing_id = max_seen_listing_id
                    alert.seen_listing_ids = list({*(alert.seen_listing_ids or []), str(numeric_listing_id)})
                row_logs.append(f"Listing sent immediately | Plate: {city} {plate_number} | Key: {key}")
                row_logs.append(f"Telegram sent successfully for {plate_number}")
                send_logs.append(f"Telegram send success for {plate_number} to {chat_id} (Release #{release_count})")
            except Exception as exc:
                error_text = str(exc)
                telegram_failed += 1
                errors.append(error_text)
                row_logs.append(f"Telegram failed for {row.get('plate_number','?')}: {error_text}")
                send_logs.append(f"Telegram send failed for {row.get('plate_number','?')}: {error_text}")

        alert.last_checked_at = now.strftime('%Y-%m-%d %H:%M:%S')
        alert.last_scan_at = alert.last_checked_at
        effective_matching_count = max(len(final_matches) - final_city_guard_skips, 0)
        alert.last_match_count = effective_matching_count
        scanned_pages = {
            (parse_qs(urlparse(str(row.get('source_url') or '')).query).get('page') or ['1'])[0]
            for row in matches
        }
        scanned_page_numbers = [int(page) for page in scanned_pages if str(page).isdigit()]
        alert.last_pages_scanned = max(scanned_page_numbers) if scanned_page_numbers else min(auto_max_pages, 1)
        alert.last_listings_found = len(matches)
        alert.last_matching_listings = effective_matching_count
        alert.last_skipped_old = old_rejects + date_rejects
        alert.last_skipped_featured = featured_rejects
        alert.last_sent = sent
        if sent:
            alert.last_sent_at = alert.last_checked_at
        alert.last_skip_reason = row_logs[-1] if row_logs else ''
        alert.last_status = 'matched' if sent else ('error' if errors else 'no_match')
        alert.sent_listing_keys = list(sent_keys)
        alert.notified_listing_keys = list(sent_keys)
        alert.seen_listing_keys = list(baseline_seen)
        alert.max_seen_listing_id = max_seen_listing_id
        alert.updated_at = now.strftime('%Y-%m-%d %H:%M:%S')
        alert = _trim_alert_model(alert)

        if stop_all_active() or not _storage_alert_enabled(str(alert.id or alert_id)):
            row_logs.append('Alert state not saved because emergency stop-all is active or the alert is disabled/missing in storage.')
            send_logs.append('Scheduler cache/storage guard prevented stale alert state from being re-saved.')
        else:
            save_alert(alert.model_dump())

        summary_lines = [
            f"Alert ID: {alert.id or '(missing)'}",
            f"Alert name: {_alert_display_name(alert)}",
            f"Alert city: {alert_city_log}",
            f"Enabled: {'yes' if alert.enabled else 'no'}",
            f"Raw matches: {len(matches)}",
            f"Pages scanned: {alert.last_pages_scanned}",
            f"Unique listings: {len(unique_matches)}",
            f"Filtered listings: {effective_matching_count}",
            f"Matched city: {matched_city_count}",
            f"Skipped city mismatch: {city_mismatch_rejects}",
            f"Final city guard skips: {final_city_guard_skips}",
            f"Notifications queued: {len(to_notify)}",
            f"Sent: {sent}",
            f"Telegram ready: {telegram_ready}",
        ]
        if city_missing_rejects:
            summary_lines.append(f"Skipped city missing: {city_missing_rejects}")
        if final_city_guard_skips:
            summary_lines.append(f"Final send guard city skips: {final_city_guard_skips}")
        if price_rejects:
            summary_lines.append(f"Rejected by price filter: {price_rejects}")
        if sold_rejects:
            summary_lines.append(f"Skipped sold listings: {sold_rejects}")
        if featured_rejects:
            summary_lines.append(f"Skipped featured listings: {featured_rejects}")
        if old_rejects:
            summary_lines.append(f"Skipped old listings: {old_rejects}")
        if already_notified_rejects:
            summary_lines.append(f"Skipped already notified: {already_notified_rejects}")
        if date_rejects:
            summary_lines.append(f"Skipped older than baseline/enabled time: {date_rejects}")
        if duplicate_send_skips:
            summary_lines.append(f"Skipped duplicate/cooldown: {duplicate_send_skips}")
        if row_logs:
            summary_lines.append(f"Listing details: {'; '.join(row_logs[:5])}" + ("..." if len(row_logs) > 5 else ""))
        if send_logs:
            summary_lines.append(f"Send details: {'; '.join(send_logs[:5])}" + ("..." if len(send_logs) > 5 else ""))
        if errors:
            summary_lines.append(f"Errors: {'; '.join(errors)}")
        eligible_to_send = max(len(to_notify) - duplicate_send_skips - final_city_guard_skips, 0)
        skipped_baseline = old_rejects
        skipped_old = old_rejects + date_rejects
        if sent == 0:
            row_logs.append(f"Scan completed: {len(unique_matches)} listings found, {effective_matching_count} matched filters, {city_mismatch_rejects} skipped city mismatch, {skipped_old} skipped old/baseline, 0 sent.")
        row_logs.extend([
            f'Alert ID: {alert.id or "(missing)"}',
            f'Alert name: {_alert_display_name(alert)}',
            f'Alert city: {alert_city_log}',
            f"Enabled: {'yes' if alert.enabled else 'no'}",
            f'Total listings found: {len(matches)}',
            f'Skipped city mismatch: {city_mismatch_rejects}',
            f'Final city guard skips: {final_city_guard_skips}',
            f'Matched city: {matched_city_count}',
            f'Sent: {sent}',
            f'Eligible to send: {eligible_to_send}',
            f'Telegram sent: {sent}',
            f'Listings sent: {sent}',
            f'Telegram failed: {telegram_failed}',
            'Alert decision completed',
        ])
        row_logs.append('Scan completed')

        log = AlertLog(
            id=str(uuid.uuid4()),
            alert_id=alert.id,
            alert_name=alert.name,
            checked_at=now.strftime('%Y-%m-%d %H:%M:%S'),
            status=alert.last_status,
            event_type='Sent' if sent else ('Error' if errors else ('No match' if not to_notify else 'Skipped')),
            severity='success' if sent else ('error' if errors else 'warning'),
            message=' | '.join(summary_lines),
            matches_count=effective_matching_count,
            sent_notifications=sent,
            error='; '.join(errors) if errors else '',
            listing=to_notify[0][1] if to_notify else {},
            reason=_match_reason(alert) if sent else ('Telegram failed. See error details.' if errors else 'No new matching listing after baseline and duplicate checks.'),
            details=[*row_logs[:300], *send_logs[:100]]
        )
        add_alert_log(log.model_dump())
        total_scraped_count = len(matches)
        queued_count = len(to_notify)
        decision_logs_response = row_logs[:200]
        print(
            f"Scan finished: alert_id={alert.id or '(missing)'} "
            f"name={_alert_display_name(alert)} listings_found={total_scraped_count} "
            f"skipped_old={skipped_old} sent={sent} error={'; '.join(errors) if errors else 'none'}"
        )
        matches.clear()
        unique_matches.clear()
        final_matches.clear()
        to_notify.clear()
        row_logs.clear()
        send_logs.clear()

        if queued_count == 0:
            message = f"Run completed: {effective_matching_count} listings found, 0 new after baseline. Nothing was sent."
            if effective_matching_count:
                message += " No Telegram messages sent because all listings were already in baseline."
        elif telegram_failed and not sent:
            message = f"Run completed: {effective_matching_count} listings found, {queued_count} new listing(s) found, but Telegram failed: {'; '.join(errors)}."
        elif telegram_failed:
            message = f"Run completed: {effective_matching_count} listings found, {queued_count} new after baseline, {sent} sent, {telegram_failed} failed."
        else:
            message = f"Run completed: {effective_matching_count} listings found, {queued_count} new listing(s) sent to Telegram." if sent else f"Run completed: {effective_matching_count} listings found, {queued_count} new after baseline, 0 sent."

        if not errors:
            LAST_ERROR = None
        return {
            'ok': True,
            'total_scraped': total_scraped_count,
            'scraped': total_scraped_count,
            'matched': effective_matching_count,
            'new_after_baseline': queued_count,
            'skipped_baseline': skipped_baseline,
            'eligible_to_send': eligible_to_send,
            'sent': sent,
            'failed': telegram_failed,
            'telegram_failed': telegram_failed,
            'skipped_old': skipped_old,
            'skipped_featured': featured_rejects,
            'skipped_city_mismatch': city_mismatch_rejects,
            'skipped_city_missing': city_missing_rejects,
            'final_city_guard_skips': final_city_guard_skips,
            'matched_city': matched_city_count,
            'skipped_duplicate': duplicate_send_skips,
            'skipped_price': price_rejects,
            'telegram_ready': telegram_ready,
            'telegram_attempts': telegram_attempts,
            'telegram_token_found': bool(bot_token),
            'telegram_channel_found': bool(chat_id),
            'errors': errors,
            'decision_logs': decision_logs_response,
            'message': message,
        }
    except MemoryError as exc:
        LAST_ERROR = f"MemoryError while scanning alert {alert_id}"
        now = datetime.utcnow()
        add_alert_log(AlertLog(
            id=str(uuid.uuid4()),
            alert_id=alert_id,
            alert_name=alert.name,
            checked_at=now.strftime('%Y-%m-%d %H:%M:%S'),
            status='error',
            event_type='Error',
            severity='error',
            message=LAST_ERROR,
            matches_count=0,
            sent_notifications=0,
            error=LAST_ERROR,
            reason='Alert check failed because memory was exhausted.',
            details=[*_alert_identity_lines(alert), LAST_ERROR],
        ).model_dump())
        print(LAST_ERROR)
        matches.clear()
        return {'ok': False, 'error': LAST_ERROR}
    except Exception as exc:
        LAST_ERROR = str(exc)
        now = datetime.utcnow()
        log = AlertLog(
            id=str(uuid.uuid4()),
            alert_id=alert_id,
            alert_name=alert.name,
            checked_at=now.strftime('%Y-%m-%d %H:%M:%S'),
            status='error',
            event_type='Error',
            severity='error',
            message=str(exc),
            matches_count=0,
            sent_notifications=0,
            error=str(exc),
            reason='Alert check failed.',
            details=[
                *_alert_identity_lines(alert),
                str(exc),
            ]
        )
        add_alert_log(log.model_dump())
        print(f"Alert check failed for {alert_id}: {exc}")
        traceback.print_exc()
        matches.clear()
        return {'ok': False, 'error': str(exc)}


def _check_due_alerts():
    global LAST_SCAN_TIME, LAST_ERROR, LAST_PLATE_CLEANUP_DATE
    alerts = get_alerts()
    now = datetime.utcnow()
    LAST_SCAN_TIME = now.strftime('%Y-%m-%d %H:%M:%S')
    if stop_all_active():
        clear_scheduler_cache()
        print("Alert scheduler scan skipped: emergency stop-all is active. No Telegram sends will run.")
        return
    if not alerts:
        clear_scheduler_cache()
        print("Alert scheduler scan: no alerts found in storage. No Telegram sends will run.")
        return
    enabled_alerts = [a for a in alerts if _is_enabled_value(a.get('enabled'))]
    active_ids = [str(a.get('id') or '') for a in enabled_alerts]
    active_names = [str(a.get('name') or a.get('id') or '(unnamed)') for a in enabled_alerts]
    active_cities = [
        str(a.get('cities') or a.get('city') or 'All cities')
        for a in enabled_alerts
    ]
    print(f"Alerts loaded count: {len(alerts)}")
    print(f"Enabled alerts count: {len(enabled_alerts)}")
    print(f"Alert scheduler scan active alert IDs: {', '.join(active_ids) if active_ids else '(none)'}")
    print(f"Active alert names: {', '.join(active_names) if active_names else '(none)'}")
    print(f"Active alert cities: {', '.join(active_cities) if active_cities else '(none)'}")
    if not enabled_alerts:
        clear_scheduler_cache()
        print("Alert scheduler scan: no enabled alerts in storage. No Telegram sends will run.")
        return
    config = get_config()
    today = now.strftime('%Y-%m-%d')
    if LAST_PLATE_CLEANUP_DATE != today:
        deleted = plate_tracking.cleanup_old_plates(config.cleanup_old_plates_days)
        LAST_PLATE_CLEANUP_DATE = today
        print(f"Plate tracking cleanup: deleted {deleted} records older than {config.cleanup_old_plates_days} days")
    for a in alerts:
        try:
            print(f"Alert scheduler scan rule: id={a.get('id') or '(missing)'} name={a.get('name') or '(unnamed)'} cities={a.get('cities') or a.get('city') or 'All cities'} enabled={'yes' if _is_enabled_value(a.get('enabled')) else 'no'}")
            if not _is_enabled_value(a.get('enabled')):
                alert_id = str(a.get('id') or '').strip()
                if alert_id and alert_id not in DISABLED_SKIP_LOGGED:
                    alert = Alert(**_ensure_alert_city_fields(a))
                    DISABLED_SKIP_LOGGED.add(alert_id)
                    add_alert_log(AlertLog(
                        id=str(uuid.uuid4()),
                        alert_id=alert.id,
                        alert_name=alert.name,
                        checked_at=now.strftime('%Y-%m-%d %H:%M:%S'),
                        status='disabled',
                        event_type='Skipped',
                        severity='warning',
                        message=f"Scheduler skipped disabled alert rule: {_alert_display_name(alert)}. No scan and no Telegram send.",
                        matches_count=0,
                        sent_notifications=0,
                        error='',
                        listing={},
                        reason='Alert is disabled.',
                        details=[
                            *_alert_identity_lines(alert),
                            'Scheduler skipped disabled alert.',
                            'No scan performed.',
                            'No Telegram messages sent.',
                        ],
                    ).model_dump())
                continue
            if a.get('id'):
                DISABLED_SKIP_LOGGED.discard(str(a.get('id')))
            last = a.get('last_checked_at')
            interval_seconds = _get_interval_seconds(a)
            due = False
            if not last:
                due = True
            else:
                try:
                    last_dt = datetime.strptime(last, '%Y-%m-%d %H:%M:%S')
                    due = now >= last_dt + timedelta(seconds=interval_seconds)
                except Exception:
                    due = True
            alert_id = str(a.get('id') or '').strip()
            if due and RUNNING_ALERTS.get(alert_id):
                print(f"Alert scheduler skipped active scan: id={alert_id or '(missing)'} name={a.get('name') or '(unnamed)'}")
                continue
            if due:
                RUNNING_ALERTS[alert_id] = True
                try:
                    print(
                        f"Scan started: alert_id={alert_id or '(missing)'} "
                        f"name={a.get('name') or '(unnamed)'} cities={a.get('cities') or a.get('city') or 'All cities'} "
                        f"interval={interval_seconds}s"
                    )
                    result = check_alert(a)
                    if not result.get('ok'):
                        LAST_ERROR = str(result.get('error') or 'Alert scan failed')
                finally:
                    if stop_all_active():
                        RUNNING_ALERTS.pop(alert_id, None)
                    else:
                        RUNNING_ALERTS[alert_id] = False
        except MemoryError:
            LAST_ERROR = f"MemoryError in scheduler for alert {a.get('id') or '(missing)'}"
            print(LAST_ERROR)
            RUNNING_ALERTS.pop(str(a.get('id') or ''), None)
            add_alert_log(AlertLog(
                id=str(uuid.uuid4()),
                alert_id=str(a.get('id') or ''),
                alert_name=str(a.get('name') or ''),
                checked_at=now.strftime('%Y-%m-%d %H:%M:%S'),
                status='error',
                event_type='Error',
                severity='error',
                message=LAST_ERROR,
                matches_count=0,
                sent_notifications=0,
                error=LAST_ERROR,
                reason='Scheduler memory protection caught MemoryError.',
                details=['Scheduler caught MemoryError.', 'Scheduler will continue with future runs.'],
            ).model_dump())
            continue
        except Exception as exc:
            LAST_ERROR = str(exc)
            print(f"Alert scheduler error for id={a.get('id') or '(missing)'}: {exc}")
            traceback.print_exc()
            RUNNING_ALERTS.pop(str(a.get('id') or ''), None)
            add_alert_log(AlertLog(
                id=str(uuid.uuid4()),
                alert_id=str(a.get('id') or ''),
                alert_name=str(a.get('name') or ''),
                checked_at=now.strftime('%Y-%m-%d %H:%M:%S'),
                status='error',
                event_type='Error',
                severity='error',
                message=f"Scheduler error: {exc}",
                matches_count=0,
                sent_notifications=0,
                error=str(exc),
                reason='Scheduler caught an alert exception and continued.',
                details=[traceback.format_exc()],
            ).model_dump())
            continue


def start_scheduler():
    global SCHEDULER
    if SCHEDULER is not None:
        return SCHEDULER
    alerts = get_alerts()
    settings = get_settings()
    telegram_configured = bool(str(settings.get('telegram_bot_token', '') or '').strip() and normalize_telegram_channel_id(settings.get('telegram_chat_id', '') or settings.get('telegram_channel_id', '')))
    print(f"Alert storage path: {ALERTS_PATH}")
    print(f"Alert data directory: {DATA_DIR}")
    print(f"Alerts loaded count: {len(alerts)}")
    print(f"Enabled alerts count: {len([alert for alert in alerts if _is_enabled_value(alert.get('enabled'))])}")
    print(f"Telegram configured: {'yes' if telegram_configured else 'no'}")
    SCHEDULER = BackgroundScheduler()
    SCHEDULER.add_job(_check_due_alerts, 'interval', seconds=10, id='alerts_checker', max_instances=1, coalesce=True)
    SCHEDULER.start()
    print(f"Scheduler started: {'yes' if SCHEDULER.running else 'no'}")
    return SCHEDULER


def stop_scheduler():
    global SCHEDULER
    if SCHEDULER:
        try:
            SCHEDULER.shutdown(wait=False)
        except Exception:
            pass
        SCHEDULER = None
