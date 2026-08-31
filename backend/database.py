import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.config import DB_PATH, get_default_download_dir

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Settings table with user_id support
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT,
        key TEXT,
        value TEXT,
        PRIMARY KEY (user_id, key)
    )
    """)
    
    # Download History table with user_id
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        title TEXT,
        filename TEXT,
        file_path TEXT,
        source_url TEXT,
        file_size INTEGER,
        formatted_size TEXT,
        duration INTEGER,
        resolution TEXT,
        quality TEXT,
        status TEXT,
        created_at TEXT,
        completed_at TEXT
    )
    """)
    
    # Safe column migration check if tables already existed without user_id
    try:
        cursor.execute("SELECT user_id FROM history LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE history ADD COLUMN user_id TEXT DEFAULT 'default'")
        
    conn.commit()
    conn.close()

def get_setting(key: str, default: Optional[str] = None, user_id: str = "default") -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
    row = cursor.fetchone()
    if not row and user_id != "default":
        # Fallback to default
        cursor.execute("SELECT value FROM settings WHERE user_id = 'default' AND key = ?", (key,))
        row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def save_setting(key: str, value: str, user_id: str = "default"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?)
    ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
    """, (user_id, key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings(user_id: str = "default") -> Dict[str, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    # Default settings
    default_settings = {
        "download_dir": get_default_download_dir(),
        "default_quality": "original",
        "default_preset": "best",
        "default_format": "mp4",
        "max_concurrent_downloads": "3",
        "theme": "dark",
        "auto_start_download": "false"
    }
    
    cursor.execute("SELECT key, value FROM settings WHERE user_id = ? OR user_id = 'default'", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    result = default_settings.copy()
    for row in rows:
        result[row["key"]] = row["value"]
    return result

def add_history_item(item: Dict[str, Any], user_id: str = "default"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO history (
        id, user_id, title, filename, file_path, source_url,
        file_size, formatted_size, duration, resolution,
        quality, status, created_at, completed_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.get("id"),
        user_id or "default",
        item.get("title", ""),
        item.get("filename", ""),
        item.get("file_path", ""),
        item.get("source_url", ""),
        item.get("file_size", 0),
        item.get("formatted_size", ""),
        item.get("duration", 0),
        item.get("resolution", ""),
        item.get("quality", "original"),
        item.get("status", "completed"),
        item.get("created_at", datetime.now().isoformat()),
        item.get("completed_at", datetime.now().isoformat())
    ))
    conn.commit()
    conn.close()

def get_history(limit: int = 50, user_id: str = "default") -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id or "default", limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_history_item(item_id: str, user_id: str = "default"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (item_id, user_id or "default"))
    conn.commit()
    conn.close()

def clear_all_history(user_id: str = "default"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id or "default",))
    conn.commit()
    conn.close()
