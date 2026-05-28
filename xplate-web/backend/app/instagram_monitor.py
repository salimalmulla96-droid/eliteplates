import html
import os
import re
import uuid
import concurrent.futures
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from PIL import Image

from .alerts import normalize_telegram_channel_id, user_friendly_telegram_error
from .storage import (
    add_alert_log,
    get_instagram_seen_posts,
    get_instagram_settings,
    get_settings,
    save_instagram_seen_posts,
    save_instagram_settings,
)

INSTAGRAM_RUNNING = False
INSTAGRAM_SCHEDULER: BackgroundScheduler | None = None
INSTAGRAM_MAX_RUNTIME_SECONDS = 45
PROVIDER_CONFIG_ERROR = "Instagram provider is not configured. Add APIFY_API_TOKEN and APIFY_ACTOR_ID first."
TELEGRAM_CONFIG_ERROR = "Telegram settings are missing. Go to Telegram settings, add Bot Token and Channel ID, then click Save."


def _clean_username(username: str) -> str:
    value = str(username or "").strip()
    value = re.sub(r"^https?://(?:www\.)?instagram\.com/", "", value, flags=re.IGNORECASE)
    value = value.split("?")[0].strip().strip("/").lstrip("@")
    return value.lower()


def _enabled_accounts(settings: dict[str, Any]) -> list[str]:
    accounts = settings.get("accounts") or []
    usernames: list[str] = []
    for item in accounts:
        if isinstance(item, str):
            username = _clean_username(item)
            enabled = True
        else:
            username = _clean_username(item.get("username", ""))
            enabled = item.get("enabled", True)
        if username and enabled and username not in usernames:
            usernames.append(username)
    return usernames


def _provider_name(settings: dict[str, Any]) -> str:
    provider = str(settings.get("instagram_provider") or settings.get("access_method") or "Apify").strip()
    return provider or "Apify"


def _apify_actor_path(actor_id: str) -> str:
    return str(actor_id or "").strip().replace("/", "~")


def _apify_config(settings: dict[str, Any]) -> tuple[str, str]:
    token = str(settings.get("apify_api_token") or "").strip()
    actor_id = str(settings.get("apify_actor_id") or "apify/instagram-post-scraper").strip()
    return token, actor_id


def _require_provider(settings: dict[str, Any]) -> tuple[str, str, str]:
    provider = _provider_name(settings)
    if provider.lower() == "apify":
        token, actor_id = _apify_config(settings)
        if not token or not actor_id:
            raise ValueError(PROVIDER_CONFIG_ERROR)
        return provider, token, actor_id
    return provider, "", ""


def _extract_meta(content: str, prop: str) -> str:
    patterns = [
        rf'<meta\s+property=["\']{re.escape(prop)}["\']\s+content=["\']([^"\']*)["\']',
        rf'<meta\s+content=["\']([^"\']*)["\']\s+property=["\']{re.escape(prop)}["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
    return ""


def _extract_latest_post_url(content: str) -> str:
    match = re.search(r"https://www\.instagram\.com/p/[A-Za-z0-9_-]+/?", content)
    return match.group(0) if match else ""


def _extract_plate_details(text: str) -> dict[str, str]:
    source = str(text or "")
    number_match = re.search(r"\b\d{2,6}\b", source)
    price_match = re.search(r"(?:AED|Dhs?\.?)\s*([\d,]+)", source, re.IGNORECASE)
    code_match = re.search(r"\b(?:code|plate code)\s*[:#-]?\s*([A-Z0-9]{1,3})\b", source, re.IGNORECASE)
    city_match = re.search(r"\b(Dubai|Abu Dhabi|Sharjah|Ajman|Fujairah|Ras Al Khaimah|Umm Al Quwain)\b", source, re.IGNORECASE)
    return {
        "plate_number": number_match.group(0) if number_match else "",
        "price": f"AED {price_match.group(1)}" if price_match else "",
        "code": code_match.group(1).upper() if code_match else "",
        "city": city_match.group(1).title() if city_match else "",
    }


def _first_value(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    return entry.strip()
                if isinstance(entry, dict):
                    nested = _first_value(entry, ["url", "src", "displayUrl", "imageUrl"])
                    if nested:
                        return nested
        if isinstance(value, dict):
            nested = _first_value(value, ["url", "src", "displayUrl", "imageUrl"])
            if nested:
                return nested
    return ""


def _sanitize_url_for_log(url: str) -> str:
    if not url:
        return ""
    return re.sub(r"([?&](?:token|access_token|signature|sig|key|api_key)=)[^&]+", r"\1[hidden]", str(url), flags=re.IGNORECASE)


def _image_candidates(item: dict[str, Any]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []

    def add(value: Any, kind: str) -> None:
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            pair = (value.strip(), kind)
            if pair not in candidates:
                candidates.append(pair)
            return
        if isinstance(value, list):
            for entry in value:
                add(entry, kind)
            return
        if isinstance(value, dict):
            for nested_key in ["displayUrl", "display_url", "imageUrl", "image_url", "url", "src"]:
                add(value.get(nested_key), f"{kind}.{nested_key}")
            for nested_key in ["versions", "candidates", "images"]:
                add(value.get(nested_key), f"{kind}.{nested_key}")

    for key in ["displayUrl", "display_url", "imageUrl", "image_url", "image", "photo", "photos", "images", "sidecar", "childPosts", "latestSidecarPosts", "thumbnailUrl", "thumbnail_url"]:
        add(item.get(key), key)
    return candidates


def _select_best_image(item: dict[str, Any]) -> tuple[str, str]:
    candidates = _image_candidates(item)
    if not candidates:
        return "", "missing"

    def score(candidate: tuple[str, str]) -> int:
        url, kind = candidate
        text = f"{kind} {url}".lower()
        value = 0
        if "display" in text or "imageurl" in text or "image_url" in text:
            value += 30
        if "thumbnail" in text or "thumb" in text:
            value -= 40
        if "s150x150" in text or "150x150" in text:
            value -= 30
        if "1080" in text or "1440" in text:
            value += 10
        return value

    return sorted(candidates, key=score, reverse=True)[0]


def _extract_instagram_phone(*texts: str) -> str:
    combined = " ".join(str(text or "") for text in texts)
    patterns = [
        r"\+971[\s().-]*5\d[\s().-]*\d{3}[\s().-]*\d{4}",
        r"\b971[\s().-]*5\d[\s().-]*\d{3}[\s().-]*\d{4}\b",
        r"\b0[\s().-]*5[\s().-]*\d[\s().-]*\d{3}[\s().-]*\d{4}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            phone = re.sub(r"[^\d+]", "", match.group(0))
            if phone.startswith("971"):
                phone = f"+{phone}"
            return phone
    return "?"


def _extract_instagram_seller(item: dict[str, Any]) -> str:
    keys = ["ownerFullName", "fullName", "sellerName", "authorName", "ownerName", "displayName", "name"]
    seller = _first_value(item, keys)
    if seller:
        return seller
    for key in ["owner", "author", "user"]:
        nested = item.get(key)
        if isinstance(nested, dict):
            seller = _first_value(nested, keys)
            if seller:
                return seller
    return "?"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "pinned", "pin"}
    return False


def _nested_value(item: dict[str, Any], path: list[str]) -> Any:
    current: Any = item
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _is_pinned_post(item: dict[str, Any]) -> bool:
    pinned_keys = ["isPinned", "pinned", "is_pinned", "isPinnedPost", "is_pinned_post"]
    if any(_truthy(item.get(key)) for key in pinned_keys):
        return True
    if any(_truthy(_nested_value(item, path)) for path in [["node", "isPinned"], ["node", "pinned"], ["edge", "isPinned"]]):
        return True
    section = str(item.get("section") or item.get("location") or item.get("position") or item.get("feedSection") or "").lower()
    return "pinned" in section


def _parse_post_timestamp(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        timestamp = float(value)
        return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    text = str(value).strip()
    if not text:
        return 0.0
    if text.isdigit():
        return _parse_post_timestamp(float(text))
    for candidate in [text, text.replace("Z", "+00:00")]:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            pass
    return 0.0


def _normalize_apify_post(item: dict[str, Any], username: str) -> dict[str, Any]:
    owner_data = item.get("owner")
    owner_username = owner_data.get("username", "") if isinstance(owner_data, dict) else ""
    owner = _clean_username(item.get("ownerUsername") or item.get("username") or owner_username) or username
    post_url = _first_value(item, ["url", "postUrl", "shortCodeUrl", "link"])
    shortcode = item.get("shortCode") or item.get("shortcode") or item.get("code")
    if not post_url and shortcode:
        post_url = f"https://www.instagram.com/p/{shortcode}/"
    timestamp = str(item.get("timestamp") or item.get("takenAt") or item.get("taken_at") or item.get("createdAt") or item.get("date") or "")
    image_url, image_url_type = _select_best_image(item)
    caption = str(item.get("caption") or item.get("text") or item.get("description") or "")
    return {
        "account": username,
        "username": owner,
        "post_url": post_url,
        "image_url": image_url,
        "image_url_type": image_url_type,
        "caption": caption,
        "seller_name": _extract_instagram_seller(item),
        "phone_number": _extract_instagram_phone(caption),
        "timestamp": timestamp,
        "shortcode": shortcode or "",
        "is_pinned": _is_pinned_post(item),
        "_sort_timestamp": _parse_post_timestamp(timestamp),
        "provider": "Apify",
        "raw": item,
    }


def _apify_input(username: str, actor_id: str) -> dict[str, Any]:
    profile_url = f"https://www.instagram.com/{username}/"
    payload = {
        "directUrls": [profile_url],
        "startUrls": [{"url": profile_url}],
        "usernames": [username],
        "username": [username],
        "profiles": [profile_url],
        "resultsType": "posts",
        "resultsLimit": 12,
        "searchType": "user",
        "addParentData": False,
    }
    if "post-scraper" in actor_id:
        payload.update({"onlyPostsNewerThan": "", "onlyPostsOlderThan": ""})
    return payload


def fetch_latest_post(username: str, settings: dict[str, Any] | None = None, details: list[str] | None = None) -> tuple[dict[str, Any], int]:
    settings = settings or get_instagram_settings()
    provider, token, actor_id = _require_provider(settings)
    username = _clean_username(username)
    if provider.lower() == "apify":
        response = requests.post(
            f"https://api.apify.com/v2/acts/{_apify_actor_path(actor_id)}/run-sync-get-dataset-items",
            params={"token": token},
            json=_apify_input(username, actor_id),
            timeout=max(5, min(int(settings.get("max_runtime_seconds") or INSTAGRAM_MAX_RUNTIME_SECONDS), 45)),
        )
        if response.status_code in {401, 403}:
            raise ValueError("Apify token is invalid or unauthorized.")
        if response.status_code >= 400:
            raise ValueError(f"Apify API error {response.status_code}: {response.text[:300]}")
        items = response.json()
        if not isinstance(items, list):
            raise ValueError("Apify returned an unexpected response.")
        posts = [_normalize_apify_post(item, username) for item in items if isinstance(item, dict)]
        posts = [post for post in posts if post.get("post_url") or post.get("image_url")]
        if not posts:
            raise ValueError("Apify returned no Instagram posts for this account.")
        pinned_skipped = [post for post in posts if post.get("is_pinned")]
        candidates = [post for post in posts if not post.get("is_pinned")]
        if not candidates:
            raise ValueError("Apify returned only pinned Instagram posts for this account.")
        candidates.sort(key=lambda post: (post.get("_sort_timestamp") or 0, post.get("timestamp") or ""), reverse=True)
        selected = candidates[0]
        selected.pop("_sort_timestamp", None)
        if details is not None:
            details.extend([
                f"Instagram debug account: {username}",
                f"Instagram debug total posts returned: {len(items)}",
                f"Instagram debug pinned posts skipped: {len(pinned_skipped)}",
                f"Instagram debug selected latest post: {selected.get('shortcode') or selected.get('post_url') or '(missing)'}",
                f"Selected latest post URL: {selected.get('post_url') or '(missing)'}",
                f"Instagram debug selected timestamp: {selected.get('timestamp') or '(missing)'}",
                f"Selected post timestamp: {selected.get('timestamp') or '(missing)'}",
            ])
        return selected, len(items)

    url = f"https://www.instagram.com/{username}/"
    response = requests.get(
        url,
        timeout=15,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    content = response.text
    post_url = _extract_latest_post_url(content) or url
    caption = _extract_meta(content, "og:description")
    return {
        "account": username,
        "username": username,
        "post_url": post_url,
        "image_url": _extract_meta(content, "og:image"),
        "image_url_type": "og:image",
        "caption": caption,
        "seller_name": "?",
        "phone_number": _extract_instagram_phone(caption),
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
    }, 1 if post_url else 0


def _post_link(post: dict[str, Any]) -> str:
    post_url = str(post.get("post_url") or "").strip()
    shortcode = str(post.get("shortcode") or "").strip()
    if post_url and re.search(r"instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+", post_url):
        return post_url
    if shortcode:
        return f"https://www.instagram.com/p/{shortcode}/"
    return post_url


def _post_key(post: dict[str, Any]) -> str:
    shortcode = str(post.get("shortcode") or post.get("shortCode") or "").strip()
    if shortcode:
        return f"shortcode:{shortcode}"
    post_id = str(post.get("id") or post.get("post_id") or post.get("postId") or "").strip()
    if post_id:
        return f"id:{post_id}"
    post_url = _post_link(post)
    if post_url:
        return f"url:{post_url}"
    image_url = str(post.get("image_url") or "").strip()
    account = _clean_username(post.get("account") or post.get("username") or "")
    return f"fallback:{account}:{image_url}"


def _seen_for_account(seen: dict[str, Any], username: str) -> list[str]:
    value = seen.get(username, [])
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return [str(item) for item in value.get("posts", [])]
    return []


def _parse_utc(value: Any) -> datetime | None:
    timestamp = _parse_post_timestamp(value)
    if timestamp:
        return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return parsed
    except Exception:
        return None


def _instagram_caption(post: dict[str, Any], settings: dict[str, Any] | None = None) -> str:
    settings = settings or {}
    username = _clean_username(post.get("username", "")) or _clean_username(post.get("account", "")) or "?"
    safe_username = html.escape(username, quote=False)
    safe_account = html.escape(_clean_username(post.get("account") or username) or "?", quote=False)
    safe_seller = html.escape(str(post.get("seller_name") or "?").strip() or "?", quote=False)
    safe_phone = html.escape(str(post.get("phone_number") or "?").strip() or "?", quote=False)
    safe_post_url = html.escape(_post_link(post), quote=True)
    lines = [
        "🚨 <b>New Instagram Post</b>",
        "",
        f"Account: {safe_account}",
        f"Username: {safe_username}",
        f"Seller: {safe_seller}",
        f"Phone: {safe_phone}",
    ]
    if settings.get("include_caption", False) and str(post.get("caption") or "").strip():
        lines.extend(["", "Caption:", html.escape(str(post.get("caption") or "").strip(), quote=False)])
    if settings.get("extract_plate_details_from_images", False):
        ocr_text = str(post.get("ocr_text") or "No readable plate text detected").strip() or "No readable plate text detected"
        lines.extend(["", "OCR enabled: yes", "OCR detected text:", html.escape(ocr_text, quote=False)])
    if safe_post_url:
        lines.extend(["", "Post:", f'<a href="{safe_post_url}">{safe_post_url}</a>'])
    return "\n".join(lines)


def _telegram_credentials() -> tuple[str, str, str]:
    global_settings = get_settings()
    bot_token = str(global_settings.get("telegram_bot_token", "") or "").strip()
    chat_id = normalize_telegram_channel_id(global_settings.get("telegram_chat_id", "") or global_settings.get("telegram_channel_id", ""))
    source = "central settings" if bot_token or chat_id else "missing"
    if not bot_token:
        bot_token = str(os.environ.get("TELEGRAM_BOT_TOKEN", "") or "").strip()
        if bot_token:
            source = "environment"
    if not chat_id:
        chat_id = normalize_telegram_channel_id(os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHANNEL_ID", ""))
        if chat_id:
            source = "environment"
    if not bot_token:
        raise ValueError(TELEGRAM_CONFIG_ERROR)
    if not chat_id:
        raise ValueError(TELEGRAM_CONFIG_ERROR)
    return bot_token, chat_id, source


def _telegram_log_details() -> tuple[list[str], bool]:
    global_settings = get_settings()
    central_token = str(global_settings.get("telegram_bot_token", "") or "").strip()
    central_chat = normalize_telegram_channel_id(global_settings.get("telegram_chat_id", "") or global_settings.get("telegram_channel_id", ""))
    env_token = str(os.environ.get("TELEGRAM_BOT_TOKEN", "") or "").strip()
    env_chat = normalize_telegram_channel_id(os.environ.get("TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHANNEL_ID", ""))
    token_found = bool(central_token or env_token)
    chat_found = bool(central_chat or env_chat)
    if central_token or central_chat:
        source = "central settings"
    elif env_token or env_chat:
        source = "environment"
    else:
        source = "missing"
    return [
        f"Telegram token loaded for Instagram: {'yes' if token_found else 'no'}",
        f"Telegram channel ID loaded for Instagram: {'yes' if chat_found else 'no'}",
        f"Telegram source: {source}",
    ], token_found and chat_found


def _raise_telegram_error(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text
        try:
            detail = response.json().get("description", detail)
        except Exception:
            pass
        raise ValueError(user_friendly_telegram_error(detail)) from exc


def _download_image(image_url: str) -> tuple[BytesIO, str]:
    response = requests.get(image_url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
    extension = "jpg"
    if "png" in content_type:
        extension = "png"
    elif "webp" in content_type:
        extension = "webp"
    return BytesIO(response.content), f"instagram.{extension}"


def _run_ocr_for_post(post: dict[str, Any], settings: dict[str, Any], details: list[str]) -> str:
    enabled = bool(settings.get("extract_plate_details_from_images", False))
    image_url = str(post.get("image_url") or "").strip()
    details.append(f"OCR enabled: {'yes' if enabled else 'no'}")
    if not enabled:
        details.append("Image downloaded: no")
        details.append("OCR result length: 0")
        details.append("OCR text preview: (skipped)")
        details.append("OCR skipped reason: OCR disabled")
        return ""
    details.append(f"Image available for OCR: {'yes' if image_url else 'no'}")
    details.append(f"OCR image URL type: {post.get('image_url_type') or 'unknown'}")
    details.append(f"OCR image URL used: {_sanitize_url_for_log(image_url) if image_url else '(missing)'}")
    if not image_url:
        details.append("Image downloaded: no")
        details.append("OCR result length: 0")
        details.append("OCR text preview: No readable plate text detected")
        details.append("OCR skipped: no image URL available")
        return "No readable plate text detected"
    downloaded = False
    try:
        import pytesseract

        image_file, _filename = _download_image(image_url)
        downloaded = True
        details.append("Image downloaded: yes")
        image_file.seek(0)
        image = Image.open(image_file)
        if max(image.size) < 900:
            scale = max(2, int(900 / max(image.size)))
            image = image.resize((image.width * scale, image.height * scale))
        text = pytesseract.image_to_string(image).strip()
        text = re.sub(r"\s+", " ", text)
        found = bool(text)
        details.append(f"OCR result found: {'yes' if found else 'no'}")
        details.append(f"OCR result length: {len(text)}")
        details.append(f"OCR text preview: {text[:180] if text else 'No readable plate text detected'}")
        return text or "No readable plate text detected"
    except Exception as exc:
        if not downloaded:
            details.append("Image downloaded: no")
        details.append(f"OCR skipped: {exc}")
        details.append("OCR result found: no")
        details.append("OCR result length: 0")
        details.append("OCR text preview: No readable plate text detected")
        return "No readable plate text detected"


def _send_instagram_post(post: dict[str, Any], settings: dict[str, Any], details: list[str]) -> None:
    bot_token, chat_id, _source = _telegram_credentials()
    caption = _instagram_caption(post, settings)
    image_url = str(post.get("image_url") or "").strip()
    send_image = bool(settings.get("include_post_image", True) or settings.get("send_instagram_image_to_telegram", True))
    if not image_url or not send_image:
        details.append(f"Image URL found: {'yes' if image_url else 'no'}")
        details.append(f"Telegram image send enabled: {'yes' if send_image else 'no'}")
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=20,
        )
        _raise_telegram_error(response)
        details.append("Telegram send result: sent via sendMessage")
        return

    details.append("Image URL found: yes")
    details.append("Telegram image send enabled: yes")
    send_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    response = requests.post(
        send_url,
        json={"chat_id": chat_id, "photo": image_url, "caption": caption, "parse_mode": "HTML"},
        timeout=20,
    )
    if response.ok:
        details.append("Telegram send result: sent via sendPhoto")
        return

    details.append(f"Telegram sendPhoto by URL failed: {response.text[:200]}")
    try:
        image_file, filename = _download_image(image_url)
        upload_response = requests.post(
            send_url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": (filename, image_file)},
            timeout=30,
        )
        _raise_telegram_error(upload_response)
        details.append("Telegram send result: sent via sendPhoto upload")
    except Exception as exc:
        details.append(f"Telegram sendPhoto failure: {exc}")
        raise


def _log(status: str, message: str, severity: str = "warning", sent: int = 0, failed: int = 0, error: str = "", details: list[str] | None = None, listing: dict[str, Any] | None = None) -> None:
    add_alert_log({
        "id": str(uuid.uuid4()),
        "alert_id": "instagram",
        "alert_name": "Instagram Monitoring",
        "checked_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "event_type": "Sent" if sent else ("Error" if error else "Match"),
        "severity": severity,
        "message": message,
        "matches_count": sent + failed,
        "sent_notifications": sent,
        "error": error,
        "listing": listing or {},
        "reason": "Instagram monitoring check.",
        "details": details or [],
    })


def verify_instagram_provider(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_instagram_settings()
    provider = _provider_name(settings)
    token, actor_id = _apify_config(settings)
    result = {
        "ok": False,
        "provider_connected": False,
        "provider": provider,
        "token_found": bool(token),
        "actor_id_found": bool(actor_id),
        "actor_id": actor_id,
        "last_provider_error": "",
    }
    if provider.lower() == "apify" and (not token or not actor_id):
        result["last_provider_error"] = PROVIDER_CONFIG_ERROR
    elif provider.lower() == "apify":
        try:
            response = requests.get("https://api.apify.com/v2/users/me", params={"token": token}, timeout=15)
            if response.ok:
                result["ok"] = True
                result["provider_connected"] = True
            else:
                result["last_provider_error"] = f"Apify verification failed: {response.status_code} {response.text[:200]}"
        except Exception as exc:
            result["last_provider_error"] = str(exc)
    else:
        result["ok"] = True
        result["provider_connected"] = True
    save_instagram_settings({
        **settings,
        "provider_connected": result["provider_connected"],
        "last_provider_error": result["last_provider_error"],
    })
    return result


def _provider_log_details(settings: dict[str, Any], account_count: int, started: bool = False) -> list[str]:
    provider = _provider_name(settings)
    token, actor_id = _apify_config(settings)
    details = []
    details.append("Instagram monitoring started")
    if started:
        details.append("Send latest Instagram posts started")
    details.extend([
        f"Accounts count: {account_count}",
        f"Accounts loaded: {account_count}",
        f"Instagram monitoring enabled: {'yes' if settings.get('enabled') else 'no'}",
        f"Send all new posts enabled: {'yes' if settings.get('send_all_new_posts') else 'no'}",
        f"instagram_activated_at: {settings.get('instagram_activated_at') or '(missing)'}",
        f"Provider selected: {provider}",
        f"Provider connected: {'yes' if settings.get('provider_connected') else 'no'}",
        f"Apify token found: {'yes' if token else 'no'}",
        f"Apify actor ID: {actor_id or '(missing)'}",
    ])
    return details


def run_instagram_check(ignore_baseline: bool = False) -> dict[str, Any]:
    settings = get_instagram_settings()
    accounts = _enabled_accounts(settings)
    if not settings.get("enabled", False) and not ignore_baseline:
        return {"ok": True, "message": "Instagram monitoring is disabled.", "checked": 0, "sent": 0, "failed": 0, "posts": []}
    if not settings.get("send_all_new_posts", True) and not ignore_baseline:
        return {"ok": True, "message": "Instagram post sending is disabled.", "checked": 0, "sent": 0, "failed": 0, "posts": []}
    if settings.get("enabled", False) and not settings.get("baseline_completed", False) and not ignore_baseline:
        return reset_instagram_baseline(message="Instagram baseline saved. Only future posts will be sent.")

    details = _provider_log_details(settings, len(accounts), started=ignore_baseline)
    if ignore_baseline:
        details.append("Manual Instagram send.")
    telegram_details, telegram_ready = _telegram_log_details()
    details.extend(telegram_details)
    if not telegram_ready:
        details.append(f"Final summary: 0 accounts checked, 0 sent, {len(accounts)} failed.")
        _log("instagram_telegram_missing", TELEGRAM_CONFIG_ERROR, "error", failed=len(accounts), error=TELEGRAM_CONFIG_ERROR, details=details)
        return {"ok": False, "message": TELEGRAM_CONFIG_ERROR, "checked": 0, "sent": 0, "failed": len(accounts), "posts": [], "errors": [TELEGRAM_CONFIG_ERROR]}
    try:
        _require_provider(settings)
    except Exception as exc:
        details.append(f"Final summary: 0 accounts checked, 0 sent, {len(accounts)} failed.")
        save_instagram_settings({**settings, "last_provider_error": str(exc), "provider_connected": False})
        _log("instagram_provider_error", str(exc), "error", failed=len(accounts), error=str(exc), details=details)
        return {"ok": False, "message": str(exc), "checked": 0, "sent": 0, "failed": len(accounts), "posts": [], "errors": [str(exc)]}

    seen = get_instagram_seen_posts() or settings.get("seen_instagram_posts") or {}
    activated_at = _parse_utc(settings.get("instagram_activated_at"))
    posts: list[dict[str, Any]] = []
    sent = 0
    failed = 0
    errors: list[str] = []
    checked = 0
    for index, username in enumerate(accounts, start=1):
        details.append(f"Processing account {index}/{len(accounts)}: {username}")
        try:
            post, returned = fetch_latest_post(username, settings, details)
            checked += 1
            details.append(f"Posts returned: {returned}")
            details.append(f"Account checked: {username}")
            details.append(f"Total posts returned: {returned}")
            details.append(f"Selected latest non-pinned post: {post.get('shortcode') or _post_link(post) or '(missing)'}")
            details.append(f"Post upload timestamp: {post.get('timestamp') or '(missing)'}")
            if settings.get("extract_plate_numbers", False):
                post["detected_plate"] = _extract_plate_details(post.get("caption", ""))
            post["ocr_text"] = _run_ocr_for_post(post, settings, details)
            post["account"] = username
            post["username"] = _clean_username(post.get("username", "")) or username or "?"
            post["seller_name"] = str(post.get("seller_name") or "?").strip() or "?"
            post["phone_number"] = _extract_instagram_phone(post.get("caption", ""), post.get("ocr_text", ""))
            posts.append(post)
            key = _post_key(post)
            account_seen = _seen_for_account(seen, username)
            already_seen = key in account_seen
            posted_dt = _parse_utc(post.get("timestamp"))
            after_activation = True
            if activated_at and posted_dt:
                after_activation = posted_dt > activated_at
            elif activated_at and not posted_dt:
                after_activation = not already_seen
            details.append(f"Current baseline post: {(account_seen or [''])[0] or '(none)'}")
            details.append(f"Already seen: {'yes' if already_seen else 'no'}")
            details.append(f"Is post after activation: {'yes' if after_activation else 'no'}")
            only_ocr_matches = bool(settings.get("only_send_when_ocr_detects_plate_text", False))
            ocr_allows_send = not only_ocr_matches or (post.get("ocr_text") and post.get("ocr_text") != "No readable plate text detected")
            skip_reason = ""
            should_send = False
            if ignore_baseline:
                should_send = True
            elif already_seen:
                skip_reason = "already in Instagram baseline"
            elif not after_activation:
                skip_reason = "uploaded before Instagram activation"
            elif not ocr_allows_send:
                skip_reason = "OCR did not detect required plate text"
            elif not settings.get("send_all_new_posts", True):
                skip_reason = "Send all new Instagram posts is off"
            else:
                should_send = True
            if should_send:
                details.extend([
                    f"Instagram send selected account: {username}",
                    f"Instagram send selected post URL: {_post_link(post) or '(missing)'}",
                    f"Instagram send username found: {'yes' if post.get('username') and post.get('username') != '?' else 'no'}",
                    f"Instagram send seller found: {'yes' if post.get('seller_name') and post.get('seller_name') != '?' else 'no'}",
                    f"Instagram send phone found: {'yes' if post.get('phone_number') and post.get('phone_number') != '?' else 'no'}",
                    f"Instagram send OCR enabled: {'yes' if settings.get('extract_plate_details_from_images', False) else 'no'}",
                    f"Instagram send OCR result found: {'yes' if post.get('ocr_text') and post.get('ocr_text') != 'No readable plate text detected' else 'no'}",
                ])
                _send_instagram_post(post, settings, details)
                details.append("Telegram sent: yes")
                sent += 1
            else:
                details.append("Telegram sent: no")
                details.append(f"Skip reason: {skip_reason or 'not eligible'}")
            if key and should_send and not ignore_baseline:
                account_seen = list(dict.fromkeys([key, *account_seen]))[:100]
                seen[username] = account_seen
        except Exception as exc:
            failed += 1
            errors.append(f"{username}: {exc}")
            details.append(f"Telegram sendPhoto failure" if "Telegram" in str(exc) else f"Account failed: {exc}")

    message = f"{checked} accounts checked, {sent} sent, {failed} failed."
    details.append(f"Final summary: {message}")
    settings["last_checked_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    settings["last_instagram_scan_at"] = settings["last_checked_at"]
    settings["seen_instagram_posts"] = seen
    settings["provider_connected"] = not errors or sent > 0 or checked > 0
    settings["last_provider_error"] = "; ".join(errors)
    save_instagram_settings(settings)
    save_instagram_seen_posts(seen)
    status = "instagram_error" if failed and not sent else "instagram_sent" if sent else "instagram_checked"
    _log(
        status,
        message,
        "error" if failed and not sent else "success" if sent else "warning",
        sent=sent,
        failed=failed,
        error="; ".join(errors),
        details=details,
        listing=posts[0] if posts else {},
    )
    return {"ok": failed == 0 or sent > 0 or checked > 0, "message": message, "checked": checked, "sent": sent, "failed": failed, "posts": posts, "errors": errors}


def reset_instagram_baseline(message: str = "Instagram baseline reset. Future posts only.") -> dict[str, Any]:
    settings = get_instagram_settings()
    accounts = _enabled_accounts(settings)
    details = _provider_log_details(settings, len(accounts))
    try:
        _require_provider(settings)
    except Exception as exc:
        _log("instagram_provider_error", str(exc), "error", failed=len(accounts), error=str(exc), details=details)
        return {"ok": False, "message": str(exc), "posts": [], "errors": [str(exc)]}

    seen: dict[str, Any] = {}
    posts: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, username in enumerate(accounts, start=1):
        details.append(f"Processing account {index}/{len(accounts)}: {username}")
        try:
            post, returned = fetch_latest_post(username, settings, details)
            details.append(f"Posts returned: {returned}")
            details.append(f"Account checked: {username}")
            details.append(f"Total posts returned: {returned}")
            details.append(f"Selected latest non-pinned post: {post.get('shortcode') or _post_link(post) or '(missing)'}")
            details.append(f"Post upload timestamp: {post.get('timestamp') or '(missing)'}")
            key = _post_key(post)
            if key:
                seen[username] = [key]
                details.append(f"Current baseline post: {key}")
            posts.append(post)
        except Exception as exc:
            errors.append(f"{username}: {exc}")
            details.append(f"Account failed: {exc}")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    settings["baseline_completed"] = True
    settings["instagram_activated_at"] = now
    settings["instagram_baseline_created_at"] = now
    settings["last_baseline_reset_at"] = now
    settings["last_instagram_scan_at"] = now
    settings["last_checked_at"] = now
    settings["seen_instagram_posts"] = seen
    settings["last_provider_error"] = "; ".join(errors)
    save_instagram_settings(settings)
    save_instagram_seen_posts(seen)
    _log("instagram_baseline", message, "warning", failed=len(errors), error="; ".join(errors), details=[*details, "Current Instagram posts were saved as already seen.", "Telegram sent: no"])
    return {"ok": not errors or bool(posts), "message": message, "posts": posts, "errors": errors, "settings": settings}


def send_latest_from_all_accounts() -> dict[str, Any]:
    settings = get_instagram_settings()
    settings["send_all_new_posts"] = True
    save_instagram_settings(settings)
    result = run_instagram_check(ignore_baseline=True)
    result["message"] = result.get("message") or "Manual Instagram send."
    return result


def debug_latest_ocr() -> dict[str, Any]:
    settings = get_instagram_settings()
    if not settings.get("extract_plate_details_from_images", False):
        return {"ok": False, "message": "OCR detection is disabled."}
    posts = []
    details: list[str] = []
    for username in _enabled_accounts(settings):
        post, _returned = fetch_latest_post(username, settings, details)
        post["ocr_text"] = _run_ocr_for_post(post, settings, details)
        posts.append(post)
    return {"ok": True, "message": f"OCR debug prepared for {len(posts)} post(s).", "posts": posts, "details": details}


def _check_due_instagram() -> None:
    global INSTAGRAM_RUNNING
    if INSTAGRAM_RUNNING:
        _log(
            "instagram_skipped_active",
            "Instagram check skipped because previous run is still active.",
            "warning",
            details=["Instagram check skipped because previous run is still active."],
        )
        return
    settings = get_instagram_settings()
    if not settings.get("enabled", False):
        return
    last = settings.get("last_checked_at")
    interval = max(int(settings.get("check_interval_minutes") or 10), 1)
    due = not last
    if last:
        try:
            due = datetime.utcnow() >= datetime.strptime(last, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=interval)
        except Exception:
            due = True
    if due:
        INSTAGRAM_RUNNING = True
        try:
            max_runtime = max(5, min(int(settings.get("max_runtime_seconds") or INSTAGRAM_MAX_RUNTIME_SECONDS), 120))
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(run_instagram_check)
            try:
                future.result(timeout=max_runtime)
            except concurrent.futures.TimeoutError:
                _log(
                    "instagram_timeout",
                    f"Instagram check timed out after {max_runtime} seconds.",
                    "error",
                    error=f"Instagram check timed out after {max_runtime} seconds.",
                    details=[f"Instagram max runtime seconds: {max_runtime}", "Instagram check ended by scheduler timeout."],
                )
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        finally:
            INSTAGRAM_RUNNING = False


def start_instagram_scheduler():
    global INSTAGRAM_SCHEDULER
    if INSTAGRAM_SCHEDULER is not None:
        return INSTAGRAM_SCHEDULER
    INSTAGRAM_SCHEDULER = BackgroundScheduler()
    INSTAGRAM_SCHEDULER.add_job(_check_due_instagram, "interval", minutes=2, id="instagram_checker", max_instances=1, coalesce=True)
    INSTAGRAM_SCHEDULER.start()
    return INSTAGRAM_SCHEDULER


def stop_instagram_scheduler():
    global INSTAGRAM_SCHEDULER
    if INSTAGRAM_SCHEDULER:
        try:
            INSTAGRAM_SCHEDULER.shutdown(wait=False)
        except Exception:
            pass
        INSTAGRAM_SCHEDULER = None
