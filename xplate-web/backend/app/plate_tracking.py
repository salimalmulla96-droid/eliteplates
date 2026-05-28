"""
Plate Tracking and Duplicate Detection Module

Tracks unique plates across releases and manages cooldown periods to prevent
duplicate Telegram alerts for the same listing.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import logging

from .storage import DATA_DIR

logger = logging.getLogger(__name__)

# Path to the database
DB_PATH = DATA_DIR / 'plate_tracking.db'


def init_db():
    """Initialize the SQLite database for plate tracking."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Create plates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_id TEXT UNIQUE NOT NULL,
                city TEXT NOT NULL,
                code TEXT NOT NULL,
                plate_number TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_telegram_sent_at TEXT,
                total_releases INTEGER DEFAULT 1,
                current_price TEXT,
                seller_name TEXT,
                seller_username TEXT,
                listing_link TEXT,
                created_timestamp REAL NOT NULL,
                updated_timestamp REAL NOT NULL
            )
        ''')
        
        # Create alert_history table (tracks which alerts sent which plates)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT NOT NULL,
                plate_id TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                created_timestamp REAL NOT NULL,
                FOREIGN KEY (plate_id) REFERENCES plates(plate_id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Plate tracking database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize plate tracking database: {e}")
        raise


def get_plate_id(city: str, code: str, plate_number: str) -> str:
    """
    Generate a unique plate ID from city, code, and plate number.
    
    Args:
        city: City name (e.g., "Dubai")
        code: Plate code (e.g., "V")
        plate_number: Plate number (e.g., "51115")
    
    Returns:
        Unique plate identifier (e.g., "dubai_v_51115")
    """
    city_norm = city.strip().lower().replace(' ', '_')
    code_norm = code.strip().lower().replace(' ', '_')
    plate_norm = plate_number.strip().lower().replace(' ', '_')
    return f"{city_norm}_{code_norm}_{plate_norm}"


def track_plate(
    city: str,
    code: str,
    plate_number: str,
    price: str = "",
    seller_name: str = "",
    seller_username: str = "",
    listing_link: str = ""
) -> dict[str, Any]:
    """
    Track or update a plate in the database.
    
    Args:
        city: City name
        code: Plate code
        plate_number: Plate number
        price: Current price (optional)
        seller_name: Seller name (optional)
        seller_username: Seller username (optional)
        listing_link: Listing URL (optional)
    
    Returns:
        Plate tracking record
    """
    plate_id = get_plate_id(city, code, plate_number)
    now = datetime.utcnow()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    now_ts = now.timestamp()
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Check if plate exists
        cursor.execute('SELECT * FROM plates WHERE plate_id = ?', (plate_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing plate (increment release counter)
            cursor.execute('''
                UPDATE plates 
                SET last_seen_at = ?,
                    total_releases = total_releases + 1,
                    current_price = ?,
                    seller_name = ?,
                    seller_username = ?,
                    listing_link = ?,
                    updated_timestamp = ?
                WHERE plate_id = ?
            ''', (now_str, price, seller_name, seller_username, listing_link, now_ts, plate_id))
            
            # Fetch updated record
            cursor.execute('SELECT * FROM plates WHERE plate_id = ?', (plate_id,))
            row = cursor.fetchone()
        else:
            # Create new plate record
            cursor.execute('''
                INSERT INTO plates (
                    plate_id, city, code, plate_number,
                    first_seen_at, last_seen_at,
                    total_releases, current_price,
                    seller_name, seller_username, listing_link,
                    created_timestamp, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                plate_id, city, code, plate_number,
                now_str, now_str,
                1, price,
                seller_name, seller_username, listing_link,
                now_ts, now_ts
            ))
            
            # Fetch new record
            cursor.execute('SELECT * FROM plates WHERE plate_id = ?', (plate_id,))
            row = cursor.fetchone()
        
        conn.commit()
        conn.close()
        
        return _row_to_dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to track plate {plate_id}: {e}")
        raise


def should_send_telegram(
    city: str,
    code: str,
    plate_number: str,
    cooldown_seconds: int = 420,  # 7 minutes default
    alert_id: Optional[str] = None
) -> tuple[bool, dict[str, Any]]:
    """
    Determine if a Telegram alert should be sent for this plate.
    
    Returns:
        (should_send: bool, plate_info: dict)
        - should_send=True if this is a new plate or cooldown has passed
        - plate_info contains tracking data
    """
    plate_id = get_plate_id(city, code, plate_number)
    now = datetime.utcnow()
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM plates WHERE plate_id = ?', (plate_id,))
        row = cursor.fetchone()
        plate_info = _row_to_dict(row) if row else None
        
        if not plate_info:
            # New plate - always send
            conn.close()
            return True, {}
        
        # Check if cooldown has passed
        last_sent = plate_info.get('last_telegram_sent_at')
        if not last_sent:
            # Never sent before - send now
            conn.close()
            return True, plate_info
        
        try:
            last_sent_dt = datetime.strptime(last_sent, '%Y-%m-%d %H:%M:%S')
            cooldown_dt = last_sent_dt + timedelta(seconds=cooldown_seconds)
            
            should_send = now >= cooldown_dt
            conn.close()
            return should_send, plate_info
        except Exception as e:
            logger.error(f"Failed to parse last_sent date: {e}")
            conn.close()
            return True, plate_info
            
    except Exception as e:
        logger.error(f"Failed to check should_send_telegram for {plate_id}: {e}")
        return False, {}


def mark_telegram_sent(
    city: str,
    code: str,
    plate_number: str,
    alert_id: Optional[str] = None
) -> None:
    """
    Mark that a Telegram alert was sent for this plate.
    
    Args:
        city: City name
        code: Plate code
        plate_number: Plate number
        alert_id: Alert ID that sent the message (optional, for tracking)
    """
    plate_id = get_plate_id(city, code, plate_number)
    now = datetime.utcnow()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Update plate
        cursor.execute('''
            UPDATE plates 
            SET last_telegram_sent_at = ?
            WHERE plate_id = ?
        ''', (now_str, plate_id))
        
        # Log to alert history if alert_id provided
        if alert_id:
            cursor.execute('''
                INSERT INTO alert_history (alert_id, plate_id, sent_at, created_timestamp)
                VALUES (?, ?, ?, ?)
            ''', (alert_id, plate_id, now_str, now.timestamp()))
        
        conn.commit()
        conn.close()
        logger.debug(f"Marked Telegram sent for plate {plate_id}")
    except Exception as e:
        logger.error(f"Failed to mark telegram sent for {plate_id}: {e}")
        raise


def get_plate_info(city: str, code: str, plate_number: str) -> Optional[dict[str, Any]]:
    """
    Get tracking information for a plate.
    
    Returns:
        Plate info dict or None if not found
    """
    plate_id = get_plate_id(city, code, plate_number)
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM plates WHERE plate_id = ?', (plate_id,))
        row = cursor.fetchone()
        conn.close()
        return _row_to_dict(row) if row else None
    except Exception as e:
        logger.error(f"Failed to get plate info for {plate_id}: {e}")
        return None


def cleanup_old_plates(days: int = 30) -> int:
    """
    Delete plates not seen in the specified number of days.
    
    Args:
        days: Number of days to keep
    
    Returns:
        Number of records deleted
    """
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute('DELETE FROM plates WHERE last_seen_at < ?', (cutoff_date,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info(f"Cleaned up {deleted} old plates")
        return deleted
    except Exception as e:
        logger.error(f"Failed to cleanup old plates: {e}")
        return 0


def get_plate_stats() -> dict[str, Any]:
    """
    Get statistics about tracked plates.
    
    Returns:
        Dict with counts and info
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM plates')
        total_plates = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(total_releases) FROM plates')
        total_releases = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT COUNT(*) FROM plates WHERE last_telegram_sent_at IS NOT NULL')
        alerted_plates = cursor.fetchone()[0]
        
        conn.close()
        return {
            'total_plates_tracked': total_plates,
            'total_releases_seen': total_releases,
            'plates_alerted': alerted_plates
        }
    except Exception as e:
        logger.error(f"Failed to get plate stats: {e}")
        return {}


def _row_to_dict(row: tuple) -> dict[str, Any]:
    """Convert SQLite row to dictionary."""
    if not row:
        return {}
    
    columns = [
        'id', 'plate_id', 'city', 'code', 'plate_number',
        'first_seen_at', 'last_seen_at', 'last_telegram_sent_at',
        'total_releases', 'current_price', 'seller_name',
        'seller_username', 'listing_link', 'created_timestamp', 'updated_timestamp'
    ]
    
    return {col: val for col, val in zip(columns, row)}


# Initialize database on module import
try:
    init_db()
except Exception as e:
    logger.warning(f"Database initialization skipped: {e}")
