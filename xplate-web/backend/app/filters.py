from datetime import datetime
from statistics import mean
from typing import Any

from .scraper import matches_number_format, price_to_number, sort_results


def clean_value(value: Any, fallback: str = "?") -> str:
    text = str(value or "").strip()
    if not text or text == "Not available":
        return fallback
    return text


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["phone_number"] = clean_value(row.get("phone_number"))
    row["seller_name"] = clean_value(row.get("seller_name"), "Unknown")
    row["seller_username"] = clean_value(row.get("seller_username"))
    row["price"] = clean_value(row.get("price"))
    row["code"] = clean_value(row.get("code"))
    return row


def row_datetime(row: dict[str, Any]) -> datetime:
    try:
        return datetime.strptime(
            f"{row.get('uploaded_date', '')} {row.get('uploaded_time', '')}",
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return datetime.min


def hide_duplicates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for row in rows:
        price = price_to_number(row.get("price", "")) or -1
        key = (
            row.get("plate_number"),
            row.get("code"),
            row.get("city"),
            row.get("seller_username"),
            row.get("phone_number"),
            int(price // 500) if price >= 0 else -1,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def apply_filters(rows: list[dict[str, Any]], request) -> list[dict[str, Any]]:
    filtered = [normalize_row(row) for row in rows]
    if request.code:
        filtered = [row for row in filtered if row.get("code") == request.code]
    if request.number_format and request.number_format != "Any format":
        filtered = [
            row for row in filtered
            if matches_number_format(row.get("plate_number", ""), request.number_format)
        ]
    prices = [price_to_number(row.get("price", "")) for row in filtered]
    numeric_prices = [price for price in prices if price is not None]
    if numeric_prices and request.price_position == "Below average":
        avg = mean(numeric_prices)
        filtered = [row for row in filtered if (price_to_number(row.get("price", "")) or 10**18) < avg]
    if numeric_prices and request.price_position == "Above average":
        avg = mean(numeric_prices)
        filtered = [row for row in filtered if (price_to_number(row.get("price", "")) or -1) > avg]
    if request.hide_duplicates:
        filtered = hide_duplicates(filtered)
    return sort_results(filtered, request.sort)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    prices = [price_to_number(row.get("price", "")) for row in rows]
    prices = [price for price in prices if price is not None]
    newest_row = max(rows, key=row_datetime, default={})
    return {
        "total_results": len(rows),
        "cheapest_price": min(prices) if prices else None,
        "most_expensive_price": max(prices) if prices else None,
        "average_price": round(mean(prices), 2) if prices else None,
        "cities_found": len({row.get("city") for row in rows if row.get("city")}),
        "sellers_found": len({row.get("seller_username") for row in rows if row.get("seller_username") not in {"", "?"}}),
        "with_phone": len([row for row in rows if row.get("phone_number") not in {"", "?", "Not available"}]),
        "newest_listing": (
            f"{newest_row.get('uploaded_date', '')} {newest_row.get('uploaded_time', '')}".strip()
            if newest_row else ""
        ),
    }


def seller_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        username = row.get("seller_username") or "?"
        if username == "?":
            continue
        groups.setdefault(username, []).append(row)
    summaries = []
    for username, items in groups.items():
        prices = [price_to_number(item.get("price", "")) for item in items]
        prices = [price for price in prices if price is not None]
        summaries.append({
            "seller_name": items[0].get("seller_name", "Unknown"),
            "seller_username": username,
            "phone_number": items[0].get("phone_number", "?"),
            "total_listings": len(items),
            "cheapest_listing": min(prices) if prices else None,
            "most_expensive_listing": max(prices) if prices else None,
            "cities_used": ", ".join(sorted({item.get("city", "") for item in items if item.get("city")})),
            "last_upload_date": max((item.get("uploaded_date", "") for item in items), default=""),
            "seller_link": items[0].get("seller_link", ""),
        })
    return summaries
