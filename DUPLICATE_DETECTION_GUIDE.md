# 🚨 Comprehensive Duplicate Detection System

## Overview

The Xplate Scout duplicate detection system prevents your Telegram bot from sending the same plate listing multiple times in a short period. This document explains how it works, how to configure it, and how to use it.

---

## ✨ Features

### 1. **Unique Plate Tracking**
- Each plate is uniquely identified by: **City + Code + Plate Number**
- Example: `Dubai V 51115` → `dubai_v_51115`
- Stored in SQLite database for persistence across restarts

### 2. **No Duplicate Telegram Messages**
- If the same plate appears within a cooldown period, no message is sent
- Cooldown is configurable (default: 7 minutes)
- Example:
  - Plate sent at 10:24 ✓
  - Same plate appears at 10:26 (2 min later) ✗ SKIPPED
  - Same plate appears at 12:57 (3+ hours later) ✓ SENT AGAIN

### 3. **Repost Detection**
- Tracks how many times each plate was seen/reposted
- After cooldown expires, the plate can be sent again
- Message indicates if it's new or a repost

### 4. **Release Counter**
- Every Telegram message shows total releases seen
- Example: "🔁 Total Releases Seen: 4"
- Helps you understand which plates are most active

### 5. **Configurable Cooldown**
- Presets: 20s, 30s, 1m, 5m, 7m (default), 10m, 30m, 1h, 2h, 6h, 1d
- Or use custom seconds value
- Change via environment variable or JSON config file

### 6. **Persistent Storage**
- SQLite database stores all tracking data
- Survives server restarts
- Can be cleaned up or reset via admin endpoints

---

## 🔧 Configuration

### Option 1: Environment Variables

Create a `.env` file in the root directory:

```bash
# Use a preset
DUPLICATE_COOLDOWN_PRESET=7m

# OR use custom seconds
DUPLICATE_COOLDOWN_SECONDS=420

# Enable/disable plate tracking
ENABLE_PLATE_TRACKING=true
ENABLE_DEDUP_MESSAGES=true
INCLUDE_RELEASE_COUNT=true
```

### Option 2: Configuration File

Create `alert_config.json` in the root directory:

```json
{
  "duplicate_cooldown_preset": "7m",
  "duplicate_cooldown_seconds": 420,
  "enable_plate_tracking": true,
  "enable_dedup_messages": true,
  "include_release_count": true,
  "cleanup_old_plates_days": 30,
  "max_alert_retries": 3,
  "retry_delay_seconds": 5
}
```

### Cooldown Presets

| Preset | Duration | Use Case |
|--------|----------|----------|
| `20s` | 20 seconds | Not recommended - too high volume |
| `30s` | 30 seconds | Very aggressive alerting |
| `1m` | 1 minute | High-frequency searching |
| `5m` | 5 minutes | Frequent alerts |
| `7m` | 7 minutes | **RECOMMENDED (default)** |
| `10m` | 10 minutes | Balanced, moderate volume |
| `30m` | 30 minutes | Relaxed, lower volume |
| `1h` | 1 hour | Low-frequency searching |
| `1d` | 24 hours | Once per day per plate |

---

## 📊 How It Works

### Database Schema

The system uses SQLite with two tables:

**`plates` table:**
```
- plate_id: Unique identifier (dubai_v_51115)
- city, code, plate_number: Plate details
- first_seen_at: When first detected
- last_seen_at: Most recent appearance
- last_telegram_sent_at: Last time message was sent
- total_releases: Total times seen
- current_price, seller_name, seller_username, listing_link
- created_timestamp, updated_timestamp
```

**`alert_history` table:**
```
- alert_id: Which alert triggered the send
- plate_id: Which plate was sent
- sent_at: When the message was sent
- created_timestamp
```

### Detection Flow

```
1. New plate appears: Dubai V 51115
   ├─ Check database: Not found
   ├─ Create new record: total_releases=1
   └─ SEND Telegram ✓

2. Same plate appears 2 min later
   ├─ Check database: Found
   ├─ Check cooldown: last_sent=10:24, now=10:26 (2 min < 7 min cooldown)
   ├─ Update: last_seen_at=10:26, total_releases=2
   └─ SKIP Telegram ✗

3. Same plate appears 3 hours later
   ├─ Check database: Found
   ├─ Check cooldown: last_sent=10:24, now=12:57 (3 hours > 7 min cooldown)
   ├─ Update: last_telegram_sent_at=12:57
   └─ SEND Telegram ✓ (with release counter)
```

---

## 📨 Telegram Message Format

### New Plate (First Send)
```
🚨 New Plate Published

🏷️ Plate: Dubai V 51115
📍 City: Dubai
🔢 Code: V

💰 Price: AED 185,000

👤 Seller: John Doe
🔗 Username: @johndoe
📞 Phone: +971501234567

🕒 Posted: 2026-05-25 10:24:00

✅ Reason: Sent because...

🔗 Open Listing
```

### Reposted Plate (Subsequent Sends)
```
🚨 Plate Released Again

🏷️ Plate: Dubai V 51115
📍 City: Dubai
🔢 Code: V

💰 Price: AED 185,000

👤 Seller: John Doe
🔗 Username: @johndoe
📞 Phone: +971501234567

🕒 Posted: 2026-05-25 10:24:00

🔁 Total Releases Seen: 4
⏰ Last Seen: 2026-05-25 12:57:00

✅ Reason: Sent because...

🔗 Open Listing
```

---

## 🔍 Admin Endpoints

### Get Plate Statistics
```
GET /api/admin/plate-stats

Response:
{
  "stats": {
    "total_plates_tracked": 150,
    "total_releases_seen": 425,
    "plates_alerted": 142
  },
  "timestamp": "2026-05-25 14:30:00"
}
```

### Get Specific Plate Info
```
GET /api/admin/plate-stats/dubai_v_51115

Response:
{
  "plate_info": {
    "plate_id": "dubai_v_51115",
    "city": "Dubai",
    "code": "V",
    "plate_number": "51115",
    "first_seen_at": "2026-05-25 10:24:00",
    "last_seen_at": "2026-05-25 12:57:00",
    "last_telegram_sent_at": "2026-05-25 12:57:00",
    "total_releases": 4,
    "current_price": "185000",
    "seller_name": "John Doe"
  }
}
```

### Clean Up Old Plates
```
POST /api/admin/plate-tracking/cleanup?days=30

Response:
{
  "deleted_count": 12,
  "message": "Cleaned up 12 plates not seen in 30 days"
}
```

### Reinitialize Database (⚠️ DELETES ALL DATA)
```
POST /api/admin/plate-tracking/reinit-db

Response:
{
  "ok": true,
  "message": "Plate tracking database reinitialized"
}
```

### Get Current Configuration
```
GET /api/admin/config

Response:
{
  "config": {
    "duplicate_cooldown_seconds": 420,
    "enable_plate_tracking": true,
    "enable_dedup_messages": true,
    "cleanup_old_plates_days": 30,
    "max_retries": 3,
    "retry_delay_seconds": 5,
    "include_release_count": true
  }
}
```

### Reload Configuration
```
POST /api/admin/config/reload

Response:
{
  "ok": true,
  "message": "Configuration reloaded"
}
```

---

## 🧪 Testing the System

### 1. Monitor Incoming Plates
```bash
curl http://127.0.0.1:8000/api/admin/plate-stats
```

### 2. Create a Test Alert
- Create a new alert in the UI
- Set it to a popular plate code (e.g., "V")
- Enable Telegram notifications

### 3. Watch the Behavior
- First plate send: Should receive Telegram message ✓
- Wait 2 minutes, same plate reappears: Should NOT receive message ✗
- Wait 10+ minutes, same plate again: Should receive message ✓ (with "Plate Released Again")

### 4. Check Logs
```bash
# View alert logs
curl http://127.0.0.1:8000/api/alerts/logs

# View plate stats
curl http://127.0.0.1:8000/api/admin/plate-stats
```

---

## 🐛 Troubleshooting

### Problem: Still Getting Duplicate Messages

**Solution 1:** Check if plate tracking is enabled
```bash
curl http://127.0.0.1:8000/api/admin/config
# Verify: enable_plate_tracking=true, enable_dedup_messages=true
```

**Solution 2:** Verify cooldown value
```bash
# Should show duplicate_cooldown_seconds > 0
curl http://127.0.0.1:8000/api/admin/config
```

**Solution 3:** Check plate stats
```bash
curl http://127.0.0.1:8000/api/admin/plate-stats
# If total_plates_tracked=0, database might not be initialized
```

**Solution 4:** Reinitialize database
```bash
curl -X POST http://127.0.0.1:8000/api/admin/plate-tracking/reinit-db
```

### Problem: Cooldown is Too Strict

**Solution:** Reduce the cooldown period
```bash
# Change in .env
DUPLICATE_COOLDOWN_PRESET=1m  # 1 minute instead of 7

# OR via alert_config.json
{
  "duplicate_cooldown_seconds": 60
}
```

### Problem: Want to Send Every Time (No Deduplication)

**Not Recommended**, but possible:
```bash
# Set to very short cooldown
DUPLICATE_COOLDOWN_PRESET=1s
DUPLICATE_COOLDOWN_SECONDS=1

# OR disable dedup completely
ENABLE_DEDUP_MESSAGES=false
```

### Problem: Database Growing Too Large

**Solution:** Clean up old plates
```bash
# Delete plates not seen in 7 days
curl -X POST "http://127.0.0.1:8000/api/admin/plate-tracking/cleanup?days=7"

# OR reset entire database
curl -X POST http://127.0.0.1:8000/api/admin/plate-tracking/reinit-db
```

---

## 📈 Example Scenarios

### Scenario 1: High-Traffic Plate

```
Dubai V 51115 (Premium plate, lots of interest)

10:24 - First post: SEND to Telegram ✓
        Total Releases: 1
        
10:26 - Reappears: SKIP (cooldown) ✗
        Total Releases: 2
        
10:45 - Reappears: SKIP (cooldown) ✗
        Total Releases: 3
        
11:45 - Reappears: SKIP (cooldown) ✗
        Total Releases: 4
        
12:57 - Reappears: SEND to Telegram ✓
        Total Releases: 5
        Message shows: "🔁 Total Releases Seen: 5"
```

### Scenario 2: Multiple Alerts on Same Plate

```
Alert 1: "Send all new plates"
Alert 2: "V code plates"

Dubai V 51115 appears:

→ Alert 1 triggers: Checks database
  - New plate: SEND ✓
  - Track with alert_id=alert_1
  
→ Alert 2 triggers: Checks database
  - Plate just sent by alert_1
  - Still within cooldown: SKIP ✗
  - Track that alert_2 tried but was deduplicated
```

---

## 🚀 Production Recommendations

1. **Use default cooldown (7m)**: Balanced between responsiveness and avoiding duplicates
2. **Enable release counter**: Helps understand plate activity
3. **Clean up regularly**: Delete old plates every month
4. **Monitor stats**: Check plate-stats endpoint weekly
5. **Set up alerts**: Get notified if duplicate_cooldown_seconds is 0
6. **Test thoroughly**: Run in test mode before enabling on production

---

## 📝 Code References

### Key Files

- **Main logic**: `xplate-web/backend/app/alerts.py` (check_alert function)
- **Tracking database**: `xplate-web/backend/app/plate_tracking.py`
- **Configuration**: `xplate-web/backend/app/alert_config.py`
- **API endpoints**: `xplate-web/backend/app/main.py`

### Important Functions

```python
# Track a plate appearance
plate_tracking.track_plate(city, code, plate_number, price, seller_name, seller_username, listing_link)

# Check if should send Telegram
should_send, plate_info = plate_tracking.should_send_telegram(city, code, plate_number, cooldown_seconds)

# Mark Telegram as sent
plate_tracking.mark_telegram_sent(city, code, plate_number, alert_id)

# Get plate info
info = plate_tracking.get_plate_info(city, code, plate_number)

# Get statistics
stats = plate_tracking.get_plate_stats()

# Clean up old plates
deleted = plate_tracking.cleanup_old_plates(days=30)
```

---

## 🎯 Summary

The duplicate detection system ensures:
- ✅ Same plate not sent multiple times in short period
- ✅ Persistent tracking across restarts
- ✅ Configurable cooldown periods
- ✅ Release counter in messages
- ✅ Admin endpoints for monitoring
- ✅ Easy configuration via env/config file

**Result**: Better user experience, fewer false alerts, and smarter plate tracking!
