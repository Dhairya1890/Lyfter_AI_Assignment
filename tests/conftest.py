"""
Shared test fixtures and configuration.
"""
import hmac
import hashlib
import json
import os
import pytest
from fastapi.testclient import TestClient


# Set test environment variables before importing app
os.environ["WEBHOOK_SECRET"] = "test-secret-123"
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["LOG_LEVEL"] = "DEBUG"


from app.main import app
from app.models import init_db, get_db_path
import sqlite3


@pytest.fixture(scope="function")
def client():
    """Create a test client with a fresh database for each test."""
    # Remove existing test database
    db_path = get_db_path()
    if os.path.exists(db_path):
        os.remove(db_path)
    
    # Initialize fresh database
    init_db()
    
    with TestClient(app) as c:
        yield c
    
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def webhook_secret():
    """Return the test webhook secret."""
    return "test-secret-123"


def compute_signature(secret: str, body: bytes) -> str:
    """Compute HMAC-SHA256 signature."""
    return hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()


def create_valid_message(
    message_id: str = "m1",
    from_number: str = "+919876543210",
    to_number: str = "+14155550100",
    ts: str = "2025-01-15T10:00:00Z",
    text: str = "Hello"
) -> dict:
    """Create a valid message payload."""
    return {
        "message_id": message_id,
        "from": from_number,
        "to": to_number,
        "ts": ts,
        "text": text
    }
