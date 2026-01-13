"""
Tests for the messages endpoint.
Tests pagination, filtering, and ordering.
"""
import json
import pytest
from tests.conftest import compute_signature, create_valid_message


def insert_test_message(client, webhook_secret, message_id, from_number, to_number, ts, text=None):
    """Helper function to insert a test message."""
    payload = {
        "message_id": message_id,
        "from": from_number,
        "to": to_number,
        "ts": ts,
    }
    if text is not None:
        payload["text"] = text
    
    body = json.dumps(payload).encode("utf-8")
    signature = compute_signature(webhook_secret, body)
    
    client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )


class TestMessagesBasic:
    """Test basic message listing functionality."""
    
    def test_empty_messages_returns_empty_list(self, client):
        """Test that empty database returns empty data list."""
        response = client.get("/messages")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] == 0
        assert data["limit"] == 50  # Default
        assert data["offset"] == 0  # Default
    
    def test_list_messages_returns_correct_format(self, client, webhook_secret):
        """Test that messages are returned in correct format."""
        insert_test_message(
            client, webhook_secret,
            message_id="m1",
            from_number="+919876543210",
            to_number="+14155550100",
            ts="2025-01-15T10:00:00Z",
            text="Hello"
        )
        
        response = client.get("/messages")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["data"]) == 1
        assert data["total"] == 1
        
        msg = data["data"][0]
        assert msg["message_id"] == "m1"
        assert msg["from"] == "+919876543210"
        assert msg["to"] == "+14155550100"
        assert msg["ts"] == "2025-01-15T10:00:00Z"
        assert msg["text"] == "Hello"


class TestMessagesPagination:
    """Test pagination functionality."""
    
    def test_default_limit_is_50(self, client, webhook_secret):
        """Test that default limit is 50."""
        # Insert 60 messages
        for i in range(60):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-{i:03d}",
                from_number="+1234567890",
                to_number="+0987654321",
                ts=f"2025-01-{15 + i // 24:02d}T{i % 24:02d}:00:00Z"
            )
        
        response = client.get("/messages")
        data = response.json()
        
        assert data["limit"] == 50
        assert len(data["data"]) == 50
        assert data["total"] == 60
    
    def test_custom_limit(self, client, webhook_secret):
        """Test that custom limit works."""
        for i in range(20):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-{i:03d}",
                from_number="+1234567890",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        response = client.get("/messages?limit=5")
        data = response.json()
        
        assert data["limit"] == 5
        assert len(data["data"]) == 5
        assert data["total"] == 20
    
    def test_limit_min_1(self, client):
        """Test that limit must be at least 1."""
        response = client.get("/messages?limit=0")
        assert response.status_code == 422
    
    def test_limit_max_100(self, client):
        """Test that limit cannot exceed 100."""
        response = client.get("/messages?limit=101")
        assert response.status_code == 422
    
    def test_offset(self, client, webhook_secret):
        """Test that offset works correctly."""
        for i in range(10):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-{i:03d}",
                from_number="+1234567890",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        response = client.get("/messages?limit=5&offset=5")
        data = response.json()
        
        assert data["offset"] == 5
        assert len(data["data"]) == 5
        assert data["total"] == 10
        # Should get messages 5-9 (0-indexed, sorted by ts ASC)
    
    def test_offset_min_0(self, client):
        """Test that offset must be at least 0."""
        response = client.get("/messages?offset=-1")
        assert response.status_code == 422
    
    def test_offset_beyond_total(self, client, webhook_secret):
        """Test that offset beyond total returns empty data."""
        insert_test_message(
            client, webhook_secret,
            message_id="m1",
            from_number="+1234567890",
            to_number="+0987654321",
            ts="2025-01-15T10:00:00Z"
        )
        
        response = client.get("/messages?offset=100")
        data = response.json()
        
        assert data["data"] == []
        assert data["total"] == 1  # Total still shows actual count


class TestMessagesOrdering:
    """Test message ordering."""
    
    def test_ordering_by_ts_asc(self, client, webhook_secret):
        """Test that messages are ordered by ts ASC."""
        # Insert out of order
        insert_test_message(
            client, webhook_secret, "m3", "+1234567890", "+0987654321",
            "2025-01-15T12:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321",
            "2025-01-15T10:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m2", "+1234567890", "+0987654321",
            "2025-01-15T11:00:00Z"
        )
        
        response = client.get("/messages")
        data = response.json()
        
        # Should be ordered by timestamp ASC
        assert data["data"][0]["ts"] == "2025-01-15T10:00:00Z"
        assert data["data"][1]["ts"] == "2025-01-15T11:00:00Z"
        assert data["data"][2]["ts"] == "2025-01-15T12:00:00Z"
    
    def test_ordering_by_message_id_when_same_ts(self, client, webhook_secret):
        """Test that messages with same ts are ordered by message_id ASC."""
        same_ts = "2025-01-15T10:00:00Z"
        
        # Insert with same timestamp, different message_ids
        insert_test_message(
            client, webhook_secret, "m3", "+1234567890", "+0987654321", same_ts
        )
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321", same_ts
        )
        insert_test_message(
            client, webhook_secret, "m2", "+1234567890", "+0987654321", same_ts
        )
        
        response = client.get("/messages")
        data = response.json()
        
        # Should be ordered by message_id ASC when ts is the same
        assert data["data"][0]["message_id"] == "m1"
        assert data["data"][1]["message_id"] == "m2"
        assert data["data"][2]["message_id"] == "m3"


class TestMessagesFiltering:
    """Test message filtering."""
    
    def test_filter_by_from(self, client, webhook_secret):
        """Test filtering by sender."""
        insert_test_message(
            client, webhook_secret, "m1", "+1111111111", "+0987654321",
            "2025-01-15T10:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m2", "+2222222222", "+0987654321",
            "2025-01-15T11:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m3", "+1111111111", "+0987654321",
            "2025-01-15T12:00:00Z"
        )
        
        response = client.get("/messages?from=%2B1111111111")  # URL-encoded +
        data = response.json()
        
        assert data["total"] == 2
        assert len(data["data"]) == 2
        for msg in data["data"]:
            assert msg["from"] == "+1111111111"
    
    def test_filter_by_since(self, client, webhook_secret):
        """Test filtering by timestamp."""
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321",
            "2025-01-15T09:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m2", "+1234567890", "+0987654321",
            "2025-01-15T10:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m3", "+1234567890", "+0987654321",
            "2025-01-15T11:00:00Z"
        )
        
        response = client.get("/messages?since=2025-01-15T10:00:00Z")
        data = response.json()
        
        assert data["total"] == 2
        assert all(msg["ts"] >= "2025-01-15T10:00:00Z" for msg in data["data"])
    
    def test_filter_by_text_search(self, client, webhook_secret):
        """Test text search filtering."""
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321",
            "2025-01-15T10:00:00Z", text="Hello World"
        )
        insert_test_message(
            client, webhook_secret, "m2", "+1234567890", "+0987654321",
            "2025-01-15T11:00:00Z", text="Goodbye World"
        )
        insert_test_message(
            client, webhook_secret, "m3", "+1234567890", "+0987654321",
            "2025-01-15T12:00:00Z", text="Hello Again"
        )
        
        response = client.get("/messages?q=hello")
        data = response.json()
        
        assert data["total"] == 2
        assert all("hello" in msg["text"].lower() for msg in data["data"])
    
    def test_text_search_case_insensitive(self, client, webhook_secret):
        """Test that text search is case-insensitive."""
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321",
            "2025-01-15T10:00:00Z", text="HELLO"
        )
        insert_test_message(
            client, webhook_secret, "m2", "+1234567890", "+0987654321",
            "2025-01-15T11:00:00Z", text="hello"
        )
        insert_test_message(
            client, webhook_secret, "m3", "+1234567890", "+0987654321",
            "2025-01-15T12:00:00Z", text="HeLLo"
        )
        
        response = client.get("/messages?q=HELLO")
        data = response.json()
        
        assert data["total"] == 3
    
    def test_combined_filters(self, client, webhook_secret):
        """Test combining multiple filters."""
        insert_test_message(
            client, webhook_secret, "m1", "+1111111111", "+0987654321",
            "2025-01-15T09:00:00Z", text="Hello"
        )
        insert_test_message(
            client, webhook_secret, "m2", "+1111111111", "+0987654321",
            "2025-01-15T11:00:00Z", text="Hello Again"
        )
        insert_test_message(
            client, webhook_secret, "m3", "+2222222222", "+0987654321",
            "2025-01-15T11:00:00Z", text="Hello"
        )
        
        # Filter by from, since, and text
        response = client.get(
            "/messages?from=%2B1111111111&since=2025-01-15T10:00:00Z&q=hello"
        )
        data = response.json()
        
        assert data["total"] == 1
        assert data["data"][0]["message_id"] == "m2"


class TestTotalCount:
    """Test that total count is correct."""
    
    def test_total_ignores_limit(self, client, webhook_secret):
        """Test that total count ignores limit."""
        for i in range(20):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-{i:03d}",
                from_number="+1234567890",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        response = client.get("/messages?limit=5")
        data = response.json()
        
        assert len(data["data"]) == 5
        assert data["total"] == 20  # Total should be all messages
    
    def test_total_ignores_offset(self, client, webhook_secret):
        """Test that total count ignores offset."""
        for i in range(20):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-{i:03d}",
                from_number="+1234567890",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        response = client.get("/messages?limit=5&offset=15")
        data = response.json()
        
        assert len(data["data"]) == 5
        assert data["total"] == 20  # Total should be all messages
    
    def test_total_respects_filters(self, client, webhook_secret):
        """Test that total count respects filters."""
        for i in range(10):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-a-{i}",
                from_number="+1111111111",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        for i in range(5):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-b-{i}",
                from_number="+2222222222",
                to_number="+0987654321",
                ts=f"2025-01-15T{10+i:02d}:00:00Z"
            )
        
        response = client.get("/messages?from=%2B1111111111&limit=3")
        data = response.json()
        
        assert len(data["data"]) == 3
        assert data["total"] == 10  # Total for filtered results
