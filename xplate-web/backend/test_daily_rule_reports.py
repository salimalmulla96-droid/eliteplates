from pathlib import Path

from openpyxl import load_workbook

from app import plate_tracking
from app import storage


def _listing(**overrides):
    listing = {
        "city": "Dubai",
        "code": "A",
        "plate_number": "12345",
        "price": "AED 12,000",
        "listing_link": "https://example.test/listing/1",
        "source": "Website",
        "uploaded_date": "2026-06-25",
        "uploaded_time": "10:00",
    }
    listing.update(overrides)
    return listing


def test_rule_matches_are_deduplicated_and_workbook_is_grouped(tmp_path, monkeypatch):
    database_path = tmp_path / "plate_tracking.db"
    reports_path = tmp_path / "reports"
    monkeypatch.setattr(plate_tracking, "DB_PATH", database_path)
    monkeypatch.setattr(plate_tracking, "RULE_REPORTS_DIR", reports_path)
    monkeypatch.setattr(storage, "get_alerts", lambda: [{
        "id": "rule-1",
        "name": "Dubai VIP watch",
        "enabled": True,
        "cities": ["Dubai"],
        "code": "A",
        "price_max": "15000",
    }])
    plate_tracking.init_db()

    first = _listing()
    assert plate_tracking.insert_alert_rule_match(
        "rule-1", "Dubai VIP watch", first, "2026-06-25 10:01:00"
    )
    assert not plate_tracking.insert_alert_rule_match(
        "rule-1", "Dubai VIP watch", first, "2026-06-25 10:02:00"
    )
    assert plate_tracking.insert_alert_rule_match(
        "rule-1",
        "Dubai VIP watch",
        _listing(price="AED 11,500"),
        "2026-06-25 10:03:00",
    )
    assert plate_tracking.insert_alert_rule_match(
        "rule-1",
        "Dubai VIP watch",
        _listing(listing_link="https://example.test/listing/2", uploaded_time="11:00"),
        "2026-06-25 11:01:00",
    )
    assert plate_tracking.insert_alert_rule_match(
        "rule-1",
        "Dubai VIP watch",
        _listing(
            city="Sharjah",
            code="3",
            plate_number="7777",
            price="",
            listing_link="https://example.test/listing/3",
            source="OCR Instagram",
        ),
        "2026-06-25 12:01:00",
    )

    report_path = plate_tracking.generate_daily_rule_excel_report("rule-1", "2026-06-25")
    assert report_path == Path(reports_path / "xplate_rule_report_Dubai_VIP_watch_2026-06-25.xlsx").resolve()
    workbook = load_workbook(report_path)
    assert workbook.sheetnames == ["Summary", "Dubai", "Sharjah"]

    headers = [cell.value for cell in workbook["Dubai"][1]]
    assert headers == [
        "Full Plate",
        "Digits",
        "Source",
        "Times Uploaded Today",
        "Price",
        "All Prices Seen",
        "Listing Links",
        "Notes",
    ]
    dubai_row = [cell.value for cell in workbook["Dubai"][2]]
    assert dubai_row[0] == "Dubai A 12345"
    assert dubai_row[3] == 3
    assert dubai_row[4] == 12000
    assert dubai_row[5] == "AED 12,000, AED 11,500, AED 12,000"
    assert workbook["Dubai"].freeze_panes == "A2"
    assert workbook["Dubai"].auto_filter.ref == "A1:H2"

    summary_values = {
        workbook["Summary"].cell(row=row, column=1).value: workbook["Summary"].cell(row=row, column=2).value
        for row in range(1, workbook["Summary"].max_row + 1)
    }
    assert summary_values["Report type"] == "Daily Saved Rule Report"
    assert summary_values["Rule ID"] == "rule-1"
    assert summary_values["Total unique plates"] == 2
    assert summary_values["Total listing events"] == 4
    assert summary_values["Total repeated plates"] == 1


def test_no_data_report_has_summary_only(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_tracking, "DB_PATH", tmp_path / "plate_tracking.db")
    monkeypatch.setattr(plate_tracking, "RULE_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "get_alerts", lambda: [{
        "id": "rule-empty",
        "name": "Empty rule",
        "enabled": True,
    }])
    plate_tracking.init_db()

    report_path = plate_tracking.generate_daily_rule_excel_report("rule-empty", "2026-06-25")
    workbook = load_workbook(report_path)
    assert workbook.sheetnames == ["Summary"]
    assert workbook["Summary"]["A4"].value == "No data found for this saved rule on the selected date."
