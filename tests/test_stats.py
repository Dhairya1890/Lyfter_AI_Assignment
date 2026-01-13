"""
Tests for the stats endpoint.
Tests correctness of message analytics.
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


class TestStatsEmpty:
    """Test stats with no messages."""
    
    def test_empty_stats(self, client):
        """Test stats response when no messages exist."""
        response = client.get("/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total_messages"] == 0
        assert data["senders_count"] == 0
        assert data["messages_per_sender"] == []
        assert data["first_message_ts"] is None
        assert data["last_message_ts"] is None


class TestStatsTotalMessages:
    """Test total message count."""
    
    def test_total_messages_count(self, client, webhook_secret):
        """Test that total_messages is accurate."""
        for i in range(5):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-{i}",
                from_number="+1234567890",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        response = client.get("/stats")
        data = response.json()
        
        assert data["total_messages"] == 5


class TestStatsSendersCount:
    """Test unique senders count."""
    
    def test_senders_count_unique(self, client, webhook_secret):
        """Test that senders_count counts unique senders."""
        # 3 messages from sender A
        for i in range(3):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-a-{i}",
                from_number="+1111111111",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        # 2 messages from sender B
        for i in range(2):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-b-{i}",
                from_number="+2222222222",
                to_number="+0987654321",
                ts=f"2025-01-15T{10+i:02d}:00:00Z"
            )
        
        response = client.get("/stats")
        data = response.json()
        
        assert data["senders_count"] == 2


class TestStatsMessagesPerSender:
    """Test messages per sender statistics."""
    
    def test_messages_per_sender_ordering(self, client, webhook_secret):
        """Test that messages_per_sender is ordered by count DESC."""
        # Sender A: 5 messages
        for i in range(5):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-a-{i}",
                from_number="+1111111111",
                to_number="+0987654321",
                ts=f"2025-01-15T{i:02d}:00:00Z"
            )
        
        # Sender B: 3 messages
        for i in range(3):
            insert_test_message(
                client, webhook_secret,
                message_id=f"msg-b-{i}",
                from_number="+2222222222",
                to_number="+0987654321",
                ts=f"2025-01-15T{10+i:02d}:00:00Z"
            )
        
        # Sender C: 1 message
        insert_test_message(
            client, webhook_secret,
            message_id="msg-c-0",
            from_number="+3333333333",
            to_number="+0987654321",
            ts="2025-01-15T20:00:00Z"
        )
        
        response = client.get("/stats")
        data = response.json()
        
        messages_per_sender = data["messages_per_sender"]
        
        # Should be ordered by count DESC
        assert messages_per_sender[0]["from"] == "+1111111111"
        assert messages_per_sender[0]["count"] == 5
        
        assert messages_per_sender[1]["from"] == "+2222222222"
        assert messages_per_sender[1]["count"] == 3
        
        assert messages_per_sender[2]["from"] == "+3333333333"
        assert messages_per_sender[2]["count"] == 1
    
    def test_messages_per_sender_limit_10(self, client, webhook_secret):
        """Test that messages_per_sender is limited to top 10."""
        # Create 15 different senders
        for sender_idx in range(15):
            for msg_idx in range(15 - sender_idx):  # Varying counts
                insert_test_message(
                    client, webhook_secret,
                    message_id=f"msg-{sender_idx}-{msg_idx}",
                    from_number=f"+1000000{sender_idx:04d}",
                    to_number="+0987654321",
                    ts=f"2025-01-{15 + sender_idx:02d}T{msg_idx:02d}:00:00Z"
                )
        
        response = client.get("/stats")
        data = response.json()
        
        # Should only return top 10
        assert len(data["messages_per_sender"]) == 10
        
        # First sender should have the most messages
        assert data["messages_per_sender"][0]["count"] >= data["messages_per_sender"][9]["count"]


class TestStatsTimestamps:
    """Test first and last message timestamps."""
    
    def test_first_and_last_timestamps(self, client, webhook_secret):
        """Test first_message_ts and last_message_ts are correct."""
        insert_test_message(
            client, webhook_secret, "m2", "+1234567890", "+0987654321",
            "2025-01-15T12:00:00Z"
        )
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321",
            "2025-01-10T09:00:00Z"  # Earliest
        )
        insert_test_message(
            client, webhook_secret, "m3", "+1234567890", "+0987654321",
            "2025-01-20T18:00:00Z"  # Latest
        )
        
        response = client.get("/stats")
        data = response.json()
        
        assert data["first_message_ts"] == "2025-01-10T09:00:00Z"
        assert data["last_message_ts"] == "2025-01-20T18:00:00Z"
    
    def test_single_message_timestamps(self, client, webhook_secret):
        """Test timestamps with single message."""
        insert_test_message(
            client, webhook_secret, "m1", "+1234567890", "+0987654321",
            "2025-01-15T10:00:00Z"
        )
        
        response = client.get("/stats")
        data = response.json()
        
        # Both should be the same for single message
        assert data["first_message_ts"] == "2025-01-15T10:00:00Z"
        assert data["last_message_ts"] == "2025-01-15T10:00:00Z"


class TestStatsComprehensive:
    """Comprehensive stats tests."""
    
    def test_comprehensive_stats(self, client, webhook_secret):
        """Test all stats fields together."""
        # Create diverse test data
        senders = [
            ("+1111111111", 10),  # 10 messages
            ("+2222222222", 7),   # 7 messages
            ("+3333333333", 5),   # 5 messages
        ]
        
        msg_count = 0
        for sender, count in senders:
            for i in range(count):
                insert_test_message(
                    client, webhook_secret,
                    message_id=f"msg-{sender[-4:]}-{i}",
                    from_number=sender,
                    to_number="+0987654321",
                    ts=f"2025-01-{15 + msg_count // 24:02d}T{msg_count % 24:02d}:00:00Z"
                )
                msg_count += 1
        
        response = client.get("/stats")
        data = response.json()
        
        # Total messages
        assert data["total_messages"] == 22
        
        # Unique senders
        assert data["senders_count"] == 3
        
        # Messages per sender ordering
        assert data["messages_per_sender"][0]["from"] == "+1111111111"
        assert data["messages_per_sender"][0]["count"] == 10
        assert data["messages_per_sender"][1]["from"] == "+2222222222"
        assert data["messages_per_sender"][1]["count"] == 7
        assert data["messages_per_sender"][2]["from"] == "+3333333333"
        assert data["messages_per_sender"][2]["count"] == 5
        
        # Timestamps should not be None
        assert data["first_message_ts"] is not None
        assert data["last_message_ts"] is not None
