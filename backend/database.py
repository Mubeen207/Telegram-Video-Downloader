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
    
    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Download History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
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
    
    conn.commit()
    conn.close()
    
    # Set default settings if not already set
    default_settings = {
        "download_dir": get_default_download_dir(),
        "default_quality": "original",
        "default_preset": "best",
        "default_format": "mp4",
        "max_concurrent_downloads": "3",
        "theme": "dark",
        "auto_start_download": "false"
    }
    
    for k, v in default_settings.items():
        if get_setting(k) is None:
            save_setting(k, v)

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def save_setting(key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO settings (key, value) VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings() -> Dict[str, str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

def add_history_item(item: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO history (
        id, title, filename, file_path, source_url,
        file_size, formatted_size, duration, resolution,
        quality, status, created_at, completed_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.get("id"),
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

def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_history_item(item_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

def clear_all_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    conn.commit()
    conn.close()
