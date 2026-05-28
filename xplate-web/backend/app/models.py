from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    plate_number: str = ""
    search_mode: str = "Send all new plates"
    cities: list[str] = Field(default_factory=list)
    city: str = ""
    code: str = ""
    price_min: str = ""
    price_max: str = ""
    contains: str = ""
    starts_with: str = ""
    ends_with: str = ""
    number_format: str = "Any format"
    search_depth: str = "All pages"
    sort: str = "Newest first"
    hide_duplicates: bool = True
    show_seller_details: bool = True
    price_position: str = "Any price"


class HistoryRunRequest(BaseModel):
    id: str


class FavoriteRequest(BaseModel):
    listing: dict[str, Any]


class ExportRequest(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    filename_prefix: str = "xplate_results"


class SettingsRequest(BaseModel):
    settings: dict[str, Any]


class SellerPlatesRequest(BaseModel):
    seller_username: str = ""
    seller_name: str = ""
    phone_number: str = ""
    seller_profile_url: str = ""
    seller_link: str = ""
    current_results: list[dict[str, Any]] = Field(default_factory=list)


class AlertBase(BaseModel):
    name: str = ""
    plate_number: str = ""
    search_mode: str = "exact match"
    cities: list[str] = Field(default_factory=list)
    city: str = ""
    code: str = ""
    price_min: str = ""
    price_max: str = ""
    contains: str = ""
    starts_with: str = ""
    ends_with: str = ""
    number_format: str = "Any format"
    check_interval_minutes: int = 10
    check_interval_seconds: int = 20
    monitoring_interval_seconds: int = 20
    monitoring_interval_mode: str = "preset"
    custom_interval_value: str = ""
    custom_interval_unit: str = "seconds"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_message_title: str = "New Plate Alert"
    telegram_compact_mode: bool = False
    telegram_emojis: bool = True
    telegram_include_seller_details: bool = True
    telegram_include_detected_time: bool = True
    telegram_include_match_reason: bool = True
    send_all_new_plates: bool = True
    immediate_alerts_mode: bool = True
    fast_alert_mode: bool = True
    enrich_listing_details: bool = False
    include_sold_listings: bool = False
    include_featured_listings: bool = False
    max_listings_per_scan: int = 1000
    max_pages_per_scan: int = 20
    fresh_listing_window_minutes: int = 15
    alert_once_per_listing: bool = True
    alert_only_price_below: bool = True
    alert_only_new: bool = True
    enabled: bool = True
    activated_at: str = ""
    baseline_created_at: str = ""
    baseline_created: bool = False
    max_seen_listing_id: int = 0
    last_scan_at: str = ""
    seen_listing_ids: list[str] = Field(default_factory=list)
    seen_listing_urls: list[str] = Field(default_factory=list)
    sent_listing_keys: list[str] = Field(default_factory=list)
    enabled_at: str = ""
    baseline_completed: bool = False
    seen_listing_keys: list[str] = Field(default_factory=list)


class AlertCreate(AlertBase):
    pass


class Alert(AlertBase):
    id: str = ""
    created_at: str = ""
    updated_at: str = ""
    last_checked_at: str = ""
    last_status: str = ""
    last_match_count: int = 0
    last_pages_scanned: int = 0
    last_listings_found: int = 0
    last_matching_listings: int = 0
    last_skipped_old: int = 0
    last_skipped_featured: int = 0
    last_sent: int = 0
    last_sent_at: str = ""
    sent_today: int = 0
    last_skip_reason: str = ""
    notified_listing_keys: list[str] = Field(default_factory=list)


class AlertLog(BaseModel):
    id: str = ""
    alert_id: str = ""
    alert_name: str = ""
    checked_at: str = ""
    status: str = ""
    event_type: str = ""
    severity: str = ""
    message: str = ""
    matches_count: int = 0
    sent_notifications: int = 0
    error: str = ""
    listing: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    details: list[str] = Field(default_factory=list)
