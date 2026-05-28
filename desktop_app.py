import json
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
import webbrowser

import customtkinter as ctk
import pandas as pd

from xplate_agent import (
    CITIES,
    NUMBER_FORMAT_OPTIONS,
    RESULT_COLUMNS,
    get_seller_plates,
    matches_number_format,
    save_results,
    search_xplate,
    sort_results,
)


CITY_LABELS = {
    "All cities": None,
    "Abu Dhabi": "abu dhabi",
    "Dubai": "dubai",
    "Sharjah": "sharjah",
    "Ajman": "ajman",
    "Umm Al Quwain": "umm al quwain",
    "Ras Al Khaimah": "ras al khaimah",
    "Fujairah": "fujairah",
}

CODE_OPTIONS = ["Any code", "?"] + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["AA"]
SETTINGS_PATH = Path("app_settings.json")
FAVORITES_PATH = Path("favorites.json")
SEARCH_HISTORY_PATH = Path("search_history.json")

TABLE_COLUMNS = [
    "favorite",
    "city",
    "plate_number",
    "code",
    "price",
    "seller_name",
    "seller_username",
    "phone_number",
    "uploaded_date",
    "uploaded_time",
    "age_text",
    "deal_rank",
    "listing_link",
    "seller_link",
]


def price_to_number(price: str) -> float | None:
    match = re.search(r"([0-9][0-9,]*)", str(price or ""))
    return float(match.group(1).replace(",", "")) if match else None


def format_price(value: float | None) -> str:
    return "-" if value is None else f"AED {value:,.0f}"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class CollapsibleSection(ctk.CTkFrame):
    def __init__(self, parent, title: str, expanded: bool = True):
        super().__init__(parent, fg_color="#111827", corner_radius=12)
        self.expanded = expanded
        self.header = ctk.CTkButton(
            self,
            text=("▾ " if expanded else "▸ ") + title,
            anchor="w",
            fg_color="#111827",
            hover_color="#1f2937",
            command=self.toggle,
        )
        self.header.pack(fill="x", padx=8, pady=(8, 4))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if expanded:
            self.body.pack(fill="x", padx=10, pady=(0, 10))

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.header.configure(text=("▾ " if self.expanded else "▸ ") + self.header.cget("text")[2:])
        if self.expanded:
            self.body.pack(fill="x", padx=10, pady=(0, 10))
        else:
            self.body.pack_forget()


class XplateDesktopApp(ctk.CTk):
    def __init__(self):
        self.settings = load_json(
            SETTINGS_PATH,
            {
                "theme": "Dark",
                "accent": "blue",
                "last_city": "All cities",
                "last_mode": "exact match",
                "last_format": "Any format",
                "last_sort": "Newest first",
                "history": [],
            },
        )
        ctk.set_appearance_mode(self.settings.get("theme", "Dark").lower())
        ctk.set_default_color_theme(self.settings.get("accent", "blue"))
        super().__init__()

        self.title("Xplate Plate Checker")
        self.geometry("1580x920")
        self.minsize(1280, 780)
        self.configure(fg_color="#070b16")

        self.message_queue: queue.Queue = queue.Queue()
        self.search_thread: threading.Thread | None = None
        self.results_df = pd.DataFrame(columns=RESULT_COLUMNS + ["favorite"])
        self.filtered_df = pd.DataFrame(columns=RESULT_COLUMNS + ["favorite"])
        self.debug_lines: list[str] = []
        self.favorites = load_json(FAVORITES_PATH, [])
        self.search_history = load_json(SEARCH_HISTORY_PATH, [])
        self.seller_view_active = False
        self.all_results_before_seller_view = None

        self._build_layout()
        self.after(120, self._process_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self, width=340, corner_radius=0, fg_color="#0d1424")
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.main = ctk.CTkFrame(self, fg_color="#070b16")
        self.main.grid(row=0, column=1, sticky="nsew", padx=22, pady=20)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(3, weight=1)

        self.details = ctk.CTkFrame(self, width=330, fg_color="#0d1424", corner_radius=0)
        self.details.grid(row=0, column=2, sticky="nsew")
        self.details.grid_propagate(False)

        self._build_sidebar()
        self._build_main()
        self._build_details_panel()
        self._build_context_menu()

    def _build_sidebar(self) -> None:
        brand = ctk.CTkFrame(self.sidebar, fg_color="#111827", corner_radius=18, border_width=1, border_color="#1f2a44")
        brand.pack(fill="x", padx=14, pady=(18, 12))
        ctk.CTkLabel(brand, text="◆ Xplate Scout", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=18, pady=(16, 0))
        ctk.CTkLabel(brand, text="UAE Plate Finder", text_color="#a78bfa", font=ctk.CTkFont(size=14)).pack(anchor="w", padx=18, pady=(0, 16))

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=14, pady=(0, 10))
        for label, command in [
            ("▣ Dashboard", self.show_dashboard_page),
            ("⌕ Search Plates", self.show_search_page),
            ("◴ Saved Searches", self.show_saved_searches_page),
            ("★ Favorites", self.show_favorites_page),
            ("☷ Sellers", self.show_sellers_page),
            ("⇄ Compare", self.compare_selected),
            ("⇩ Exports", self.show_exports_page),
            ("⚙ Settings", self.show_settings_page),
        ]:
            ctk.CTkButton(
                nav,
                text=label,
                anchor="w",
                height=34,
                fg_color="#111827",
                hover_color="#312e81",
                command=command,
            ).pack(fill="x", pady=3)

        search = CollapsibleSection(self.sidebar, "Search", True)
        search.pack(fill="x", padx=14, pady=7)
        self.number_entry = ctk.CTkEntry(search.body, height=38, placeholder_text="Plate number, or leave empty for format search")
        self.number_entry.pack(fill="x", pady=5)
        self.number_entry.insert(0, self.settings.get("last_number", "2007"))
        self.history_menu = ctk.CTkOptionMenu(search.body, values=self._history_values(), command=self._use_history)
        self.history_menu.pack(fill="x", pady=5)
        self.mode_menu = ctk.CTkOptionMenu(search.body, values=["contains", "starts with", "ends with", "exact match"])
        self.mode_menu.set(self.settings.get("last_mode", "exact match"))
        self.mode_menu.pack(fill="x", pady=5)
        self.search_button = ctk.CTkButton(search.body, text="Search", height=40, command=self.start_search)
        self.search_button.pack(fill="x", pady=(9, 5))
        self.clear_button = ctk.CTkButton(search.body, text="Clear", fg_color="#334155", hover_color="#475569", command=self.clear_results)
        self.clear_button.pack(fill="x", pady=5)

        filters = CollapsibleSection(self.sidebar, "Filters", True)
        filters.pack(fill="x", padx=14, pady=7)
        self.city_menu = ctk.CTkOptionMenu(filters.body, values=list(CITY_LABELS.keys()))
        self.city_menu.set(self.settings.get("last_city", "All cities"))
        self.city_menu.pack(fill="x", pady=5)
        self.code_menu = ctk.CTkOptionMenu(filters.body, values=CODE_OPTIONS, command=lambda _v: self.apply_sort_and_filter())
        self.code_menu.set("Any code")
        self.code_menu.pack(fill="x", pady=5)
        price_frame = ctk.CTkFrame(filters.body, fg_color="transparent")
        price_frame.pack(fill="x", pady=5)
        price_frame.grid_columnconfigure((0, 1), weight=1)
        self.min_price_entry = ctk.CTkEntry(price_frame, height=34, placeholder_text="Min price")
        self.min_price_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.max_price_entry = ctk.CTkEntry(price_frame, height=34, placeholder_text="Max price")
        self.max_price_entry.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        saved_format = self.settings.get("last_format", "Any format")
        if saved_format not in NUMBER_FORMAT_OPTIONS:
            saved_format = "Any format"
        self.format_menu = ctk.CTkOptionMenu(filters.body, values=NUMBER_FORMAT_OPTIONS, command=lambda _v: self.apply_sort_and_filter())
        self.format_menu.set(saved_format)
        self.format_menu.pack(fill="x", pady=5)
        ctk.CTkLabel(
            filters.body,
            text="Number Format: searches Xplate by format, then validates locally.",
            text_color="#94a3b8",
            font=ctk.CTkFont(size=11),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(0, 5))
        self.depth_menu = ctk.CTkOptionMenu(filters.body, values=["All pages", "First 10 pages", "First 5 pages", "First page only"])
        self.depth_menu.set(self.settings.get("search_depth", "All pages"))
        self.depth_menu.pack(fill="x", pady=5)
        sort_options = ["Newest first", "Oldest first", "Cheapest first", "Most expensive first", "Seller name A-Z", "City A-Z", "Code A-Z"]
        saved_sort = self.settings.get("last_sort", "Newest first")
        if saved_sort == "Highest price first":
            saved_sort = "Most expensive first"
        if saved_sort not in sort_options:
            saved_sort = "Newest first"
        self.sort_menu = ctk.CTkOptionMenu(
            filters.body,
            values=sort_options,
            command=lambda _v: self.apply_sort_and_filter(),
        )
        self.sort_menu.set(saved_sort)
        self.sort_menu.pack(fill="x", pady=5)
        self.only_phone_var = tk.BooleanVar(value=False)
        self.only_newest_var = tk.BooleanVar(value=False)
        self.hide_duplicates_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(filters.body, text="Only listings with phone number", variable=self.only_phone_var, command=self.apply_sort_and_filter).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(filters.body, text="Only newest listings", variable=self.only_newest_var, command=self.apply_sort_and_filter).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(filters.body, text="Hide likely duplicates", variable=self.hide_duplicates_var, command=self.apply_sort_and_filter).pack(anchor="w", pady=4)

        seller = CollapsibleSection(self.sidebar, "Seller Tools", False)
        seller.pack(fill="x", padx=14, pady=7)
        ctk.CTkButton(seller.body, text="View Seller Plates", command=self.view_selected_seller_plates).pack(fill="x", pady=4)
        ctk.CTkButton(seller.body, text="Open Seller Profile", fg_color="#334155", hover_color="#475569", command=self.open_seller).pack(fill="x", pady=4)
        ctk.CTkButton(seller.body, text="Copy Phone", fg_color="#334155", hover_color="#475569", command=lambda: self.copy_selected("phone_number")).pack(fill="x", pady=4)
        ctk.CTkButton(seller.body, text="Open Listing", fg_color="#334155", hover_color="#475569", command=self.open_listing).pack(fill="x", pady=4)

        export = CollapsibleSection(self.sidebar, "Export", False)
        export.pack(fill="x", padx=14, pady=7)
        ctk.CTkButton(export.body, text="Export CSV", fg_color="#0f766e", hover_color="#0d9488", command=self.export_csv).pack(fill="x", pady=4)
        ctk.CTkButton(export.body, text="Export Excel", fg_color="#166534", hover_color="#15803d", command=self.export_excel).pack(fill="x", pady=4)
        ctk.CTkButton(export.body, text="Export selected rows only", fg_color="#334155", hover_color="#475569", command=self.export_selected_rows).pack(fill="x", pady=4)

        settings = CollapsibleSection(self.sidebar, "Settings", False)
        settings.pack(fill="x", padx=14, pady=7)
        self.theme_menu = ctk.CTkOptionMenu(settings.body, values=["Dark", "Light"], command=self.change_theme)
        self.theme_menu.set(self.settings.get("theme", "Dark"))
        self.theme_menu.pack(fill="x", pady=5)
        self.accent_menu = ctk.CTkOptionMenu(settings.body, values=["blue", "green", "dark-blue"], command=self.change_accent)
        self.accent_menu.set(self.settings.get("accent", "blue"))
        self.accent_menu.pack(fill="x", pady=5)
        self.row_size_menu = ctk.CTkOptionMenu(settings.body, values=["Compact", "Comfortable"], command=lambda _v: self.update_row_size())
        self.row_size_menu.set(self.settings.get("row_size", "Comfortable"))
        self.row_size_menu.pack(fill="x", pady=5)
        self.default_depth_menu = ctk.CTkOptionMenu(settings.body, values=["All pages", "First 10 pages", "First 5 pages", "First page only"], command=self.change_default_depth)
        self.default_depth_menu.set(self.settings.get("default_search_depth", "All pages"))
        self.default_depth_menu.pack(fill="x", pady=5)
        self.save_history_var = tk.BooleanVar(value=self.settings.get("save_history", True))
        self.auto_export_var = tk.BooleanVar(value=self.settings.get("auto_export", False))
        ctk.CTkCheckBox(settings.body, text="Save search history", variable=self.save_history_var, command=self.save_settings_flags).pack(anchor="w", pady=4)
        ctk.CTkCheckBox(settings.body, text="Auto-export last results", variable=self.auto_export_var, command=self.save_settings_flags).pack(anchor="w", pady=4)
        ctk.CTkButton(settings.body, text="Clear history", fg_color="#7f1d1d", command=lambda: self._clear_history_from_settings()).pack(fill="x", pady=5)
        ctk.CTkButton(settings.body, text="Clear favorites", fg_color="#7f1d1d", command=lambda: self._clear_favorites_from_settings()).pack(fill="x", pady=5)
        ctk.CTkButton(settings.body, text="Debug logs", fg_color="#334155", hover_color="#475569", command=self.show_debug_logs).pack(fill="x", pady=5)

        self.progress = ctk.CTkProgressBar(self.sidebar, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=18)
        self.progress.set(0)

    def _build_main(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Welcome, Salim!", text_color="#a78bfa", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text="Search Plates", font=ctk.CTkFont(size=36, weight="bold")).grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(header, text="Search UAE license plates by number, seller, price, city, and format.", text_color="#94a3b8", font=ctk.CTkFont(size=15)).grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.back_button = ctk.CTkButton(header, text="Back to all results", width=145, fg_color="#334155", hover_color="#475569", command=self.back_to_all_results)
        self.back_button.grid(row=1, column=1, rowspan=2, sticky="e")
        self.back_button.grid_remove()
        ctk.CTkButton(header, text="Theme", width=88, fg_color="#1e293b", hover_color="#312e81", command=lambda: self.change_theme("Light" if self.theme_menu.get() == "Dark" else "Dark")).grid(row=0, column=1, sticky="e", padx=(0, 96))
        ctk.CTkButton(header, text="Settings", width=88, fg_color="#1e293b", hover_color="#312e81", command=self.show_settings_page).grid(row=0, column=1, sticky="e")

        self.cards = ctk.CTkFrame(self.main, fg_color="transparent")
        self.cards.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for i in range(8):
            self.cards.grid_columnconfigure(i, weight=1)
        self.metric_labels = {}
        for col, key in enumerate(["Total", "Cheapest", "Most Expensive", "Average", "Cities", "Sellers", "Newest", "With Phone"]):
            card = ctk.CTkFrame(self.cards, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#1e293b")
            card.grid(row=0, column=col, padx=4, sticky="ew")
            ctk.CTkLabel(card, text=key.upper(), text_color="#64748b", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=12, pady=(12, 2))
            value = ctk.CTkLabel(card, text="-", font=ctk.CTkFont(size=17, weight="bold"), text_color="#f8fafc")
            value.pack(anchor="w", padx=12, pady=(0, 12))
            self.metric_labels[key] = value

        tools = ctk.CTkFrame(self.main, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#1e293b")
        tools.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        tools.grid_columnconfigure(0, weight=1)
        self.filter_entry = ctk.CTkEntry(tools, height=38, placeholder_text="Global quick filter: seller, username, phone, city, code, price...")
        self.filter_entry.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        self.filter_entry.bind("<KeyRelease>", lambda _e: self.apply_sort_and_filter())
        ctk.CTkButton(tools, text="Favorite", width=95, fg_color="#a16207", hover_color="#ca8a04", command=self.toggle_favorite_selected).grid(row=0, column=1, padx=5)
        ctk.CTkButton(tools, text="Compare selected", width=135, fg_color="#334155", hover_color="#475569", command=self.compare_selected).grid(row=0, column=2, padx=5)
        ctk.CTkButton(tools, text="View Seller Plates", width=145, command=self.view_selected_seller_plates).grid(row=0, column=3, padx=5)
        ctk.CTkButton(tools, text="Reset filters", width=115, fg_color="#334155", hover_color="#475569", command=self.reset_filters).grid(row=0, column=4, padx=(5, 12))

        table_card = ctk.CTkFrame(self.main, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#1e293b")
        table_card.grid(row=3, column=0, sticky="nsew")
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(table_card, text="Results - Seller names and usernames are clickable", text_color="#e5e7eb", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, padx=14, pady=(12, 8), sticky="w")
        self.results_tree = self._create_tree(table_card)

        bottom = ctk.CTkFrame(self.main, fg_color="transparent")
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(bottom, text="Ready", text_color="#94a3b8", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")

    def _build_details_panel(self) -> None:
        ctk.CTkLabel(self.details, text="Listing Details", font=ctk.CTkFont(size=21, weight="bold")).pack(anchor="w", padx=18, pady=(24, 8))
        self.detail_text = ctk.CTkTextbox(self.details, fg_color="#111827", text_color="#e5e7eb", wrap="word")
        self.detail_text.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.detail_text.insert("1.0", "Select a listing to see details.")
        self.detail_text.configure(state="disabled")
        detail_actions = ctk.CTkFrame(self.details, fg_color="transparent")
        detail_actions.pack(fill="x", padx=16, pady=(0, 18))
        ctk.CTkButton(detail_actions, text="Open listing", command=self.open_listing).pack(fill="x", pady=4)
        ctk.CTkButton(detail_actions, text="Open seller profile", fg_color="#334155", hover_color="#475569", command=self.open_seller).pack(fill="x", pady=4)
        ctk.CTkButton(detail_actions, text="Copy phone", fg_color="#334155", hover_color="#475569", command=lambda: self.copy_selected("phone_number")).pack(fill="x", pady=4)
        ctk.CTkButton(detail_actions, text="View seller plates", fg_color="#334155", hover_color="#475569", command=self.view_selected_seller_plates).pack(fill="x", pady=4)
        ctk.CTkButton(detail_actions, text="Add/remove favorite", fg_color="#a16207", hover_color="#ca8a04", command=self.toggle_favorite_selected).pack(fill="x", pady=4)

    def _create_tree(self, parent) -> ttk.Treeview:
        style = ttk.Style()
        style.theme_use("clam")
        self.update_row_size()
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=TABLE_COLUMNS, show="headings", selectmode="extended")
        widths = {"favorite": 70, "city": 125, "plate_number": 105, "code": 65, "price": 110, "seller_name": 145, "seller_username": 170, "phone_number": 135, "uploaded_date": 112, "uploaded_time": 105, "age_text": 100, "deal_rank": 90, "listing_link": 260, "seller_link": 240}
        for column in TABLE_COLUMNS:
            tree.heading(column, text=column)
            tree.column(column, minwidth=60, width=widths.get(column, 120), stretch=True)
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.bind("<Double-1>", self.on_table_double_click)
        tree.bind("<Button-3>", self.show_context_menu)
        tree.bind("<<TreeviewSelect>>", lambda _e: self.update_details_panel())
        return tree

    def update_row_size(self) -> None:
        compact = getattr(self, "row_size_menu", None) and self.row_size_menu.get() == "Compact"
        rowheight = 28 if compact else 36
        style = ttk.Style()
        style.configure("Treeview", background="#0b1220", foreground="#e5e7eb", fieldbackground="#0b1220", rowheight=rowheight, font=("Segoe UI", 9 if compact else 10))
        style.configure("Treeview.Heading", background="#1e293b", foreground="#f8fafc", font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])

    def _build_context_menu(self) -> None:
        self.context_menu = tk.Menu(self, tearoff=0, bg="#111827", fg="#f8fafc", activebackground="#2563eb", activeforeground="#ffffff")
        for label, command in [
            ("Copy plate number", lambda: self.copy_selected("plate_number")),
            ("Copy seller name", lambda: self.copy_selected("seller_name")),
            ("Copy username", lambda: self.copy_selected("seller_username")),
            ("Copy phone", lambda: self.copy_selected("phone_number")),
            ("Open listing", self.open_listing),
            ("Open seller profile", self.open_seller),
            ("View all seller plates", self.view_selected_seller_plates),
            ("Add to favorites", self.toggle_favorite_selected),
        ]:
            self.context_menu.add_command(label=label, command=command)

    def start_search(self) -> None:
        if self.search_thread and self.search_thread.is_alive():
            messagebox.showinfo("Search running", "Please wait for the current search to finish.")
            return
        number = self.number_entry.get().strip()
        if not number and self.format_menu.get() == "Any format":
            if not messagebox.askyesno("Broad search", "No plate number or number format is selected. Search broad Xplate results anyway?"):
                return
        city_value = CITY_LABELS[self.city_menu.get()]
        cities = CITIES if city_value is None else [city_value]
        self._save_current_settings()
        self.search_button.configure(state="disabled")
        self.progress.start()
        self.debug_lines = []
        self._set_status("Searching...")
        self._clear_tree()
        selected_format = self.format_menu.get()
        args = {"number": number, "search_mode": self.mode_menu.get(), "min_price": self.min_price_entry.get().strip(), "max_price": self.max_price_entry.get().strip(), "cities": cities, "number_format": selected_format, "search_depth": self.depth_menu.get(), "sort_mode": self.sort_menu.get(), "delay_seconds": 0}
        self.search_thread = threading.Thread(target=self._search_worker, args=(args,), daemon=True)
        self.search_thread.start()

    def _search_worker(self, args: dict) -> None:
        def progress(message: str) -> None:
            self.message_queue.put(("progress", message))
        try:
            results = search_xplate(debug_callback=progress, **args)
            progress("Saving results")
            saved = save_results(results, args["number"])
            self.message_queue.put(("done", saved))
        except Exception as exc:
            self.message_queue.put(("error", str(exc)))

    def _process_queue(self) -> None:
        try:
            while True:
                kind, payload = self.message_queue.get_nowait()
                if kind == "progress":
                    self.debug_lines.append(payload)
                    self._set_status(payload)
                elif kind == "done":
                    self._handle_done(payload)
                elif kind == "error":
                    self._handle_error(payload)
        except queue.Empty:
            pass
        self.after(120, self._process_queue)

    def _handle_done(self, saved) -> None:
        df, csv_path, _xlsx_path = saved
        self.results_df = df
        self._merge_favorites()
        self.all_results_before_seller_view = None
        self.seller_view_active = False
        self.back_button.grid_remove()
        self.apply_sort_and_filter()
        self._update_metrics()
        self.progress.stop()
        self.progress.set(0)
        self.search_button.configure(state="normal")
        self._set_status(f"Done. Found {len(self.results_df)} results. Saved to {csv_path}")
        if len(self.results_df) == 0 and self.format_menu.get() != "Any format":
            messagebox.showinfo("No format matches", "No results match this number format.")
            self._set_status("No results match this number format.")
        self.save_search_history_record(len(self.results_df))
        if self.settings.get("auto_export", False):
            save_results(self.filtered_df.to_dict("records"), self.number_entry.get().strip())

    def _handle_error(self, message: str) -> None:
        self.progress.stop()
        self.progress.set(0)
        self.search_button.configure(state="normal")
        self._set_status("Search failed")
        messagebox.showerror("Search failed", message)

    def apply_sort_and_filter(self) -> None:
        if self.results_df.empty:
            self.filtered_df = self.results_df.copy()
            self._populate_tree(self.filtered_df)
            self._update_metrics()
            return
        df = pd.DataFrame(sort_results(self.results_df.to_dict("records"), self.sort_menu.get())).reindex(columns=list(dict.fromkeys(RESULT_COLUMNS + ["favorite"])))
        term = self.filter_entry.get().strip().lower()
        if term:
            searchable = ["seller_name", "seller_username", "phone_number", "city", "code", "price"]
            mask = df[searchable].fillna("").astype(str).apply(lambda row: term in " ".join(row).lower(), axis=1)
            df = df[mask]
        code = self.code_menu.get()
        if code != "Any code":
            df = df[df["code"].fillna("?") == code]
        number_format = self.format_menu.get()
        if number_format != "Any format":
            df = df[df["plate_number"].astype(str).apply(lambda value: matches_number_format(value, number_format))]
        if self.only_phone_var.get():
            df = df[~df["phone_number"].isin(["", "?", "Not available"])]
        if self.only_newest_var.get():
            dated_rows = [(index, self._row_datetime_key(row)) for index, row in df.iterrows()]
            dated_rows = [(index, value) for index, value in dated_rows if value != datetime.min]
            if dated_rows:
                newest_value = max(value for _index, value in dated_rows)
                newest_indexes = [index for index, value in dated_rows if value == newest_value]
                df = df.loc[newest_indexes]
            else:
                df = df.iloc[0:0]
        if self.hide_duplicates_var.get():
            df = self._drop_likely_duplicates(df)
        self.filtered_df = df
        self._populate_tree(self.filtered_df)
        self._update_metrics()
        if self.results_df is not None and not self.results_df.empty and self.filtered_df.empty and self.format_menu.get() != "Any format":
            self._set_status("No results match this number format.")

    def _drop_likely_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        temp = df.copy()
        temp["_price_bucket"] = temp["price"].map(price_to_number).fillna(-1).floordiv(500).astype(int)
        return temp.drop_duplicates(subset=["plate_number", "code", "city", "phone_number", "seller_username", "_price_bucket"]).drop(columns=["_price_bucket"])

    def _populate_tree(self, df: pd.DataFrame) -> None:
        self._clear_tree()
        if df.empty:
            return
        display_df = df.reindex(columns=TABLE_COLUMNS).fillna("")
        newest_key = self._newest_key(display_df)
        max_price = max([price_to_number(v) for v in display_df["price"] if price_to_number(v) is not None], default=None)
        for index, row in display_df.iterrows():
            tag = "evenrow" if index % 2 == 0 else "oddrow"
            if row.get("deal_rank") == "Cheapest":
                tag = "cheapest"
            elif max_price is not None and price_to_number(row.get("price")) == max_price:
                tag = "expensive"
            elif self._row_datetime_key(row) == newest_key:
                tag = "newest"
            self.results_tree.insert("", "end", values=[row[column] for column in TABLE_COLUMNS], tags=(tag,))
        self.results_tree.tag_configure("evenrow", background="#0b1220")
        self.results_tree.tag_configure("oddrow", background="#101a2e")
        self.results_tree.tag_configure("cheapest", background="#12352f")
        self.results_tree.tag_configure("expensive", background="#3b1d12")
        self.results_tree.tag_configure("newest", background="#112b4a")

    def _row_datetime_key(self, row) -> datetime:
        try:
            return datetime.strptime(f"{row.get('uploaded_date', '')} {row.get('uploaded_time', '')}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return datetime.min

    def _newest_key(self, df: pd.DataFrame) -> datetime:
        keys = [self._row_datetime_key(row) for _, row in df.iterrows()]
        return max(keys, default=datetime.min)

    def _clear_tree(self) -> None:
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

    def _update_metrics(self) -> None:
        df = self.filtered_df
        prices = [price_to_number(price) for price in df["price"]] if not df.empty else []
        prices = [price for price in prices if price is not None]
        sellers = df["seller_name"].replace(["Unknown", ""], pd.NA).dropna() if not df.empty else []
        newest = "-"
        if not df.empty:
            newest_pairs = [(self._row_datetime_key(row), row) for _, row in df.iterrows()]
            newest_value, newest_row = max(newest_pairs, key=lambda item: item[0])
            if newest_value != datetime.min:
                newest = f"{newest_row.get('uploaded_date', '-')} {newest_row.get('uploaded_time', '')}".strip()
        values = {
            "Total": str(len(df)),
            "Cheapest": format_price(min(prices) if prices else None),
            "Most Expensive": format_price(max(prices) if prices else None),
            "Average": format_price(sum(prices) / len(prices) if prices else None),
            "Cities": str(df["city"].nunique() if not df.empty else 0),
            "Sellers": str(sellers.nunique() if not df.empty else 0),
            "Newest": newest,
            "With Phone": str((~df["phone_number"].isin(["", "?", "Not available"])).sum() if not df.empty else 0),
        }
        for key, value in values.items():
            self.metric_labels[key].configure(text=value)

    def selected_rows(self) -> list[dict[str, str]]:
        rows = []
        for item in self.results_tree.selection():
            rows.append(dict(zip(TABLE_COLUMNS, self.results_tree.item(item, "values"))))
        return rows

    def selected_row(self) -> dict[str, str] | None:
        rows = self.selected_rows()
        return rows[0] if rows else None

    def get_clicked_column(self, event) -> str:
        column_id = self.results_tree.identify_column(event.x)
        try:
            index = int(column_id.replace("#", "")) - 1
        except ValueError:
            return ""
        return TABLE_COLUMNS[index] if 0 <= index < len(TABLE_COLUMNS) else ""

    def on_table_double_click(self, event) -> None:
        item = self.results_tree.identify_row(event.y)
        if item:
            self.results_tree.selection_set(item)
            self.results_tree.focus(item)
        column = self.get_clicked_column(event)
        if column in {"seller_name", "seller_username"}:
            self.show_seller_filtered_view()
        elif column == "seller_link":
            self.open_seller()
        else:
            self.open_listing()

    def show_context_menu(self, event) -> None:
        item = self.results_tree.identify_row(event.y)
        if item:
            self.results_tree.selection_set(item)
            self.results_tree.focus(item)
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def show_seller_filtered_view(self) -> None:
        row = self.selected_row()
        if not row:
            return
        username = row.get("seller_username", "")
        if not username or username in {"?", "Not available"}:
            messagebox.showinfo("Seller", "No seller username available for this row.")
            return
        if not self.seller_view_active:
            self.all_results_before_seller_view = self.results_df.copy()
        self.results_df = self.results_df[self.results_df["seller_username"] == username].copy()
        self.seller_view_active = True
        self.back_button.grid()
        self.apply_sort_and_filter()
        self.show_seller_summary(row)

    def back_to_all_results(self) -> None:
        if self.all_results_before_seller_view is not None:
            self.results_df = self.all_results_before_seller_view.copy()
        self.seller_view_active = False
        self.back_button.grid_remove()
        self.apply_sort_and_filter()

    def show_seller_summary(self, row: dict[str, str]) -> None:
        df = self.results_df
        prices = [price_to_number(v) for v in df["price"] if price_to_number(v) is not None]
        summary = (
            f"Seller name: {row.get('seller_name', 'Unknown')}\n"
            f"Username: {row.get('seller_username', '?')}\n"
            f"Phone: {row.get('phone_number', '?')}\n"
            f"Total listings found: {len(df)}\n"
            f"Cheapest listing: {format_price(min(prices) if prices else None)}\n"
            f"Most expensive listing: {format_price(max(prices) if prices else None)}\n"
            f"Cities used: {', '.join(sorted(df['city'].dropna().unique()))}\n"
            f"Last upload date: {df['uploaded_date'].max() if not df.empty else '-'}"
        )
        messagebox.showinfo("Seller Summary", summary)

    def open_listing(self) -> None:
        row = self.selected_row()
        if row and row.get("listing_link"):
            webbrowser.open(row["listing_link"])

    def open_seller(self) -> None:
        row = self.selected_row()
        if row and row.get("seller_link"):
            webbrowser.open(row["seller_link"])

    def view_selected_seller_plates(self) -> None:
        row = self.selected_row()
        if not row:
            messagebox.showinfo("No row selected", "Select a result row first.")
            return
        seller_link = row.get("seller_link", "")
        if not seller_link:
            messagebox.showinfo("Seller Plates", "No seller profile link available for this seller.")
            return
        SellerPlatesWindow(self, row)

    def copy_selected(self, column: str) -> None:
        row = self.selected_row()
        if not row:
            return
        self.clipboard_clear()
        self.clipboard_append(row.get(column, ""))
        self._set_status(f"Copied {column}")

    def toggle_favorite_selected(self) -> None:
        row = self.selected_row()
        if not row:
            return
        link = row.get("listing_link", "")
        existing = {item.get("listing_link") for item in self.favorites}
        if link in existing:
            self.favorites = [item for item in self.favorites if item.get("listing_link") != link]
            self._set_status("Removed favorite")
        else:
            self.favorites.append(row)
            self._set_status("Saved favorite")
        save_json(FAVORITES_PATH, self.favorites)
        self._merge_favorites()
        self.apply_sort_and_filter()

    def _merge_favorites(self) -> None:
        favorite_links = {item.get("listing_link") for item in self.favorites}
        if "favorite" not in self.results_df.columns:
            self.results_df["favorite"] = ""
        self.results_df["favorite"] = self.results_df["listing_link"].apply(lambda link: "Fav" if link in favorite_links else "")

    def compare_selected(self) -> None:
        rows = self.selected_rows()
        if len(rows) < 2:
            messagebox.showinfo("Compare selected", "Select at least two rows to compare.")
            return
        lines = []
        for row in rows:
            lines.append(
                f"{row.get('city')} {row.get('code')} {row.get('plate_number')} | "
                f"{row.get('price')} | {row.get('seller_name')} | {row.get('uploaded_date')} {row.get('uploaded_time')} | {row.get('phone_number')}"
            )
        messagebox.showinfo("Compare selected", "\n\n".join(lines))

    def update_details_panel(self) -> None:
        row = self.selected_row()
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        if not row:
            self.detail_text.insert("1.0", "Select a listing to see details.")
        else:
            text = "\n".join([f"{key}: {row.get(key, '')}" for key in TABLE_COLUMNS])
            self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def clear_results(self) -> None:
        self.results_df = pd.DataFrame(columns=RESULT_COLUMNS + ["favorite"])
        self.filtered_df = pd.DataFrame(columns=RESULT_COLUMNS + ["favorite"])
        self._clear_tree()
        self.debug_lines = []
        for label in self.metric_labels.values():
            label.configure(text="-")
        self._set_status("Ready")

    def reset_filters(self) -> None:
        self.filter_entry.delete(0, "end")
        self.code_menu.set("Any code")
        self.format_menu.set("Any format")
        self.sort_menu.set("Newest first")
        self.only_phone_var.set(False)
        self.only_newest_var.set(False)
        self.hide_duplicates_var.set(True)
        self.apply_sort_and_filter()
        self._set_status("Filters reset")

    def export_csv(self) -> None:
        self._export_dataframe(self.filtered_df, excel=False)

    def export_excel(self) -> None:
        self._export_dataframe(self.filtered_df, excel=True)

    def export_selected_rows(self) -> None:
        rows = self.selected_rows()
        if not rows:
            messagebox.showinfo("Export selected", "Select one or more rows first.")
            return
        self._export_dataframe(pd.DataFrame(rows), excel=True)

    def _export_dataframe(self, df: pd.DataFrame, excel: bool) -> None:
        if df.empty:
            messagebox.showinfo("No results", "No visible results to export.")
            return
        saved = save_results(df.to_dict("records"), self.number_entry.get().strip())
        path = saved[2] if excel else saved[1]
        messagebox.showinfo("Export complete", f"Saved:\n{path}")

    def show_debug_logs(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Debug logs")
        window.geometry("780x440")
        textbox = ctk.CTkTextbox(window, fg_color="#0f172a", text_color="#cbd5e1")
        textbox.pack(fill="both", expand=True, padx=14, pady=14)
        textbox.insert("1.0", "\n".join(self.debug_lines) if self.debug_lines else "No debug logs yet.")
        textbox.configure(state="disabled")

    def change_theme(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())
        self.settings["theme"] = value
        save_json(SETTINGS_PATH, self.settings)

    def change_accent(self, value: str) -> None:
        self.settings["accent"] = value
        save_json(SETTINGS_PATH, self.settings)
        messagebox.showinfo("Accent color", "Accent changes apply fully after restarting the app.")

    def change_default_depth(self, value: str) -> None:
        self.settings["default_search_depth"] = value
        self.settings["search_depth"] = value
        self.depth_menu.set(value)
        save_json(SETTINGS_PATH, self.settings)

    def save_settings_flags(self) -> None:
        self.settings["save_history"] = bool(self.save_history_var.get())
        self.settings["auto_export"] = bool(self.auto_export_var.get())
        save_json(SETTINGS_PATH, self.settings)

    def _clear_history_from_settings(self) -> None:
        self.search_history = []
        save_json(SEARCH_HISTORY_PATH, self.search_history)
        messagebox.showinfo("Settings", "Search history cleared.")

    def _clear_favorites_from_settings(self) -> None:
        self.favorites = []
        save_json(FAVORITES_PATH, self.favorites)
        self._merge_favorites()
        self.apply_sort_and_filter()
        messagebox.showinfo("Settings", "Favorites cleared.")

    def _history_values(self) -> list[str]:
        history = self.settings.get("history", [])
        return history if history else ["No history"]

    def _use_history(self, value: str) -> None:
        if value and value != "No history":
            self.number_entry.delete(0, "end")
            self.number_entry.insert(0, value)

    def _save_current_settings(self) -> None:
        number = self.number_entry.get().strip()
        history = [item for item in self.settings.get("history", []) if item != number]
        if number:
            history.insert(0, number)
        self.settings.update(
            {
                "last_number": number,
                "last_city": self.city_menu.get(),
                "last_mode": self.mode_menu.get(),
                "last_format": self.format_menu.get(),
                "last_sort": self.sort_menu.get(),
                "search_depth": self.depth_menu.get(),
                "row_size": self.row_size_menu.get(),
                "history": history[:12],
            }
        )
        save_json(SETTINGS_PATH, self.settings)

    def _set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def save_search_history_record(self, result_count: int) -> None:
        if self.settings.get("save_history", True) is False:
            return
        record = {
            "plate_number": self.number_entry.get().strip(),
            "search_mode": self.mode_menu.get(),
            "city": self.city_menu.get(),
            "code": self.code_menu.get(),
            "min_price": self.min_price_entry.get().strip(),
            "max_price": self.max_price_entry.get().strip(),
            "number_format": self.format_menu.get(),
            "search_depth": self.depth_menu.get(),
            "sort": self.sort_menu.get(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "result_count": result_count,
        }
        key_fields = ["plate_number", "search_mode", "city", "code", "min_price", "max_price", "number_format", "search_depth"]
        self.search_history = [
            item for item in self.search_history
            if any(item.get(field) != record.get(field) for field in key_fields)
        ]
        self.search_history.insert(0, record)
        self.search_history = self.search_history[:100]
        save_json(SEARCH_HISTORY_PATH, self.search_history)

    def run_history_record(self, record: dict) -> None:
        self.number_entry.delete(0, "end")
        self.number_entry.insert(0, record.get("plate_number", ""))
        self.mode_menu.set(record.get("search_mode", "exact match"))
        self.city_menu.set(record.get("city", "All cities"))
        self.code_menu.set(record.get("code", "Any code"))
        self.min_price_entry.delete(0, "end")
        self.min_price_entry.insert(0, record.get("min_price", ""))
        self.max_price_entry.delete(0, "end")
        self.max_price_entry.insert(0, record.get("max_price", ""))
        self.format_menu.set(record.get("number_format", "Any format"))
        self.depth_menu.set(record.get("search_depth", "All pages"))
        self.sort_menu.set(record.get("sort", "Newest first"))
        self.start_search()

    def show_dashboard_page(self) -> None:
        self._update_metrics()
        messagebox.showinfo("Dashboard", "Dashboard cards are shown at the top of the main screen and update after every filter/search.")

    def show_search_page(self) -> None:
        self._set_status("Search Plates page active")

    def show_saved_searches_page(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Saved Searches")
        window.geometry("1060x560")
        window.configure(fg_color="#070b16")
        columns = ["plate_number", "number_format", "city", "datetime", "result_count"]
        tree = self._popup_tree(window, columns)
        for record in self.search_history:
            tree.insert("", "end", values=[record.get(column, "") for column in columns])
        def selected_record():
            selected = tree.focus()
            if not selected:
                return None
            values = dict(zip(columns, tree.item(selected, "values")))
            for record in self.search_history:
                if record.get("datetime") == values.get("datetime"):
                    return record
            return None
        actions = ctk.CTkFrame(window, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(actions, text="Run same search", command=lambda: (self.run_history_record(selected_record()) if selected_record() else None)).pack(side="left", padx=5)
        ctk.CTkButton(actions, text="Delete", fg_color="#7f1d1d", command=lambda: self._delete_history_record(selected_record(), window)).pack(side="left", padx=5)
        ctk.CTkButton(actions, text="Clear all history", fg_color="#7f1d1d", command=lambda: self._clear_history(window)).pack(side="left", padx=5)

    def _delete_history_record(self, record: dict | None, window) -> None:
        if not record:
            return
        self.search_history = [item for item in self.search_history if item.get("datetime") != record.get("datetime")]
        save_json(SEARCH_HISTORY_PATH, self.search_history)
        window.destroy()
        self.show_saved_searches_page()

    def _clear_history(self, window) -> None:
        self.search_history = []
        save_json(SEARCH_HISTORY_PATH, self.search_history)
        window.destroy()
        self.show_saved_searches_page()

    def show_favorites_page(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Favorites")
        window.geometry("1120x600")
        window.configure(fg_color="#070b16")
        columns = ["plate_number", "code", "city", "price", "seller_name", "seller_username", "phone_number", "uploaded_date", "listing_link"]
        tree = self._popup_tree(window, columns)
        for item in self.favorites:
            tree.insert("", "end", values=[item.get(column, "") for column in columns])
        def selected_row():
            selected = tree.focus()
            return dict(zip(columns, tree.item(selected, "values"))) if selected else None
        actions = ctk.CTkFrame(window, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(actions, text="Open listing", command=lambda: webbrowser.open((selected_row() or {}).get("listing_link", ""))).pack(side="left", padx=5)
        ctk.CTkButton(actions, text="Copy phone", command=lambda: self._copy_popup((selected_row() or {}).get("phone_number", ""))).pack(side="left", padx=5)
        ctk.CTkButton(actions, text="Remove favorite", fg_color="#7f1d1d", command=lambda: self._remove_favorite((selected_row() or {}).get("listing_link", ""), window)).pack(side="left", padx=5)

    def _remove_favorite(self, listing_link: str, window) -> None:
        self.favorites = [item for item in self.favorites if item.get("listing_link") != listing_link]
        save_json(FAVORITES_PATH, self.favorites)
        self._merge_favorites()
        self.apply_sort_and_filter()
        window.destroy()
        self.show_favorites_page()

    def show_sellers_page(self) -> None:
        summary = self.build_seller_summary()
        window = ctk.CTkToplevel(self)
        window.title("Sellers")
        window.geometry("1120x600")
        window.configure(fg_color="#070b16")
        columns = ["seller_name", "seller_username", "phone_number", "total", "cheapest", "most_expensive", "cities", "last_upload", "seller_link"]
        tree = self._popup_tree(window, columns)
        for row in summary:
            tree.insert("", "end", values=[row.get(column, "") for column in columns])
        def selected_row():
            selected = tree.focus()
            return dict(zip(columns, tree.item(selected, "values"))) if selected else None
        actions = ctk.CTkFrame(window, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(actions, text="Open seller profile", command=lambda: webbrowser.open((selected_row() or {}).get("seller_link", ""))).pack(side="left", padx=5)
        ctk.CTkButton(actions, text="Copy phone", command=lambda: self._copy_popup((selected_row() or {}).get("phone_number", ""))).pack(side="left", padx=5)

    def build_seller_summary(self) -> list[dict[str, str]]:
        if self.results_df.empty:
            return []
        rows = []
        for username, group in self.results_df.groupby("seller_username", dropna=False):
            if not username or username == "?":
                continue
            prices = [price_to_number(value) for value in group["price"] if price_to_number(value) is not None]
            rows.append({
                "seller_name": group["seller_name"].iloc[0],
                "seller_username": username,
                "phone_number": group["phone_number"].iloc[0],
                "total": len(group),
                "cheapest": format_price(min(prices) if prices else None),
                "most_expensive": format_price(max(prices) if prices else None),
                "cities": ", ".join(sorted(group["city"].dropna().unique())),
                "last_upload": group["uploaded_date"].max(),
                "seller_link": group["seller_link"].iloc[0],
            })
        return rows

    def show_exports_page(self) -> None:
        window = ctk.CTkToplevel(self)
        window.title("Exports")
        window.geometry("520x320")
        window.configure(fg_color="#070b16")
        panel = ctk.CTkFrame(window, fg_color="#0f172a", corner_radius=16)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(panel, text="Export Center", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=18, pady=(18, 12))
        ctk.CTkButton(panel, text="Export visible results to CSV", command=self.export_csv).pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(panel, text="Export visible results to Excel", command=self.export_excel).pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(panel, text="Export selected rows only", command=self.export_selected_rows).pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(panel, text="Export favorites", command=lambda: self._export_dataframe(pd.DataFrame(self.favorites), excel=True)).pack(fill="x", padx=18, pady=6)
        ctk.CTkButton(panel, text="Export seller summary", command=lambda: self._export_dataframe(pd.DataFrame(self.build_seller_summary()), excel=True)).pack(fill="x", padx=18, pady=6)

    def show_settings_page(self) -> None:
        messagebox.showinfo("Settings", "Settings are available in the collapsible Settings section on the left sidebar.")

    def _popup_tree(self, parent, columns: list[str]) -> ttk.Treeview:
        frame = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=16)
        frame.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=135, stretch=True)
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        y_scroll.grid(row=0, column=1, sticky="ns", pady=12)
        x_scroll.grid(row=1, column=0, sticky="ew", padx=(12, 0), pady=(0, 12))
        return tree

    def _copy_popup(self, value: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
        self._set_status("Copied")


class SellerPlatesWindow(ctk.CTkToplevel):
    COLUMNS = ["city", "plate_number", "code", "price", "uploaded_date", "uploaded_time", "age_text", "listing_link"]

    def __init__(self, parent: XplateDesktopApp, row_data: dict[str, str]):
        super().__init__(parent)
        self.row_data = row_data
        self.seller_link = row_data.get("seller_link", "")
        self.seller_name = row_data.get("seller_name") or "Unknown"
        self.seller_username = row_data.get("seller_username") or "Not available"
        self.phone_number = row_data.get("phone_number") or "?"
        self.rows: list[dict[str, str]] = []
        self.queue: queue.Queue = queue.Queue()
        self.title(f"Seller Plates - {self.seller_name}")
        self.geometry("1120x680")
        self.minsize(920, 560)
        self.configure(fg_color="#070b16")
        self.transient(parent)
        self._build_ui()
        self.after(120, self._process_queue)
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 12))
        ctk.CTkLabel(header, text=f"Seller Plates - {self.seller_name}", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text=f"{self.seller_username}  |  {self.phone_number}", text_color="#94a3b8").pack(anchor="w", pady=(4, 0))
        actions = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#1e293b")
        actions.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        for col, (text, command, color) in enumerate(
            [
                ("Open selected listing", self.open_selected_listing, "#2563eb"),
                ("Copy selected listing link", self.copy_selected_listing_link, "#334155"),
                ("Export seller plates CSV", self.export_csv, "#0f766e"),
                ("Export seller plates Excel", self.export_excel, "#166534"),
                ("Close", self.destroy, "#7f1d1d"),
            ]
        ):
            ctk.CTkButton(actions, text=text, fg_color=color, command=command).grid(row=0, column=col, padx=8, pady=12)
        table_card = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#1e293b")
        table_card.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(table_card, columns=self.COLUMNS, show="headings")
        for column in self.COLUMNS:
            self.tree.heading(column, text=column)
            self.tree.column(column, minwidth=70, width=140 if column != "listing_link" else 330, stretch=True)
        y_scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        y_scroll.grid(row=0, column=1, sticky="ns", pady=12)
        x_scroll.grid(row=1, column=0, sticky="ew", padx=(12, 0), pady=(0, 12))
        self.tree.bind("<Double-1>", lambda _event: self.open_selected_listing())
        self.status_label = ctk.CTkLabel(self, text="Loading seller plates...", text_color="#94a3b8", anchor="w")
        self.status_label.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))

    def _load_worker(self) -> None:
        try:
            self.queue.put(("done", get_seller_plates(self.seller_link, max_pages=3, timeout=10)))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def _process_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "done":
                    self.rows = payload
                    self._populate_table()
                    self.status_label.configure(text=f"Loaded {len(self.rows)} seller plates." if self.rows else "No plates found for this seller.")
                elif kind == "error":
                    self.status_label.configure(text="No plates found for this seller.")
                    messagebox.showerror("Seller Plates", payload)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(120, self._process_queue)

    def _populate_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, row in enumerate(self.rows):
            tag = "evenrow" if index % 2 == 0 else "oddrow"
            self.tree.insert("", "end", values=[row.get(column, "") for column in self.COLUMNS], tags=(tag,))
        self.tree.tag_configure("evenrow", background="#0b1220")
        self.tree.tag_configure("oddrow", background="#101a2e")

    def selected_row(self) -> dict[str, str] | None:
        selected = self.tree.focus()
        return dict(zip(self.COLUMNS, self.tree.item(selected, "values"))) if selected else None

    def open_selected_listing(self) -> None:
        row = self.selected_row()
        if row and row.get("listing_link"):
            webbrowser.open(row["listing_link"])

    def copy_selected_listing_link(self) -> None:
        row = self.selected_row()
        if row:
            self.clipboard_clear()
            self.clipboard_append(row.get("listing_link", ""))
            self.status_label.configure(text="Copied selected listing link.")

    def _export_paths(self) -> tuple[Path, Path]:
        output_dir = Path("results")
        output_dir.mkdir(exist_ok=True)
        base = self.seller_username if self.seller_username != "Not available" else self.seller_name
        safe_name = re.sub(r"[^0-9A-Za-z_-]+", "_", base).strip("_") or "seller"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        return output_dir / f"seller_plates_{safe_name}_{timestamp}.csv", output_dir / f"seller_plates_{safe_name}_{timestamp}.xlsx"

    def export_csv(self) -> None:
        if not self.rows:
            messagebox.showinfo("No plates", "No seller plates to export.")
            return
        csv_path, _ = self._export_paths()
        pd.DataFrame(self.rows).reindex(columns=self.COLUMNS).to_csv(csv_path, index=False, encoding="utf-8-sig")
        messagebox.showinfo("Export complete", f"Saved:\n{csv_path}")

    def export_excel(self) -> None:
        if not self.rows:
            messagebox.showinfo("No plates", "No seller plates to export.")
            return
        _, xlsx_path = self._export_paths()
        pd.DataFrame(self.rows).reindex(columns=self.COLUMNS).to_excel(xlsx_path, index=False)
        messagebox.showinfo("Export complete", f"Saved:\n{xlsx_path}")


if __name__ == "__main__":
    app = XplateDesktopApp()
    app.mainloop()
