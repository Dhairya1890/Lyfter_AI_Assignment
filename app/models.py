"""
Database models and SQLite initialization.
"""
import sqlite3
import os
from typing import Optional
from .config import get_settings


# SQL schema for the messages table
CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    from_msisdn TEXT NOT NULL,
    to_msisdn TEXT NOT NULL,
    ts TEXT NOT NULL,
    text TEXT,
    created_at TEXT NOT NULL
);
"""

# Create index for common query patterns
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_from ON messages(from_msisdn);
"""


def get_db_path() -> str:
    """Get the database file path from settings."""
    settings = get_settings()
    return settings.database_path


def init_db() -> None:
    """Initialize the database and create tables if they don't exist."""
    db_path = get_db_path()
    
    # Ensure the directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.executescript(CREATE_MESSAGES_TABLE)
        cursor.executescript(CREATE_INDEXES)
        conn.commit()
    finally:
        conn.close()


def get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def check_db_ready() -> bool:
    """
    Check if the database is ready (reachable and schema applied).
    Returns True if ready, False otherwise.
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if messages table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        )
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    except Exception:
        return False
