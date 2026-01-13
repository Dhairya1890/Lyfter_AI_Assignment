"""
Tests for the webhook endpoint.
Tests HMAC signature validation, payload validation, and idempotency.
"""
import json
import pytest
from tests.conftest import compute_signature, create_valid_message


class TestWebhookSignature:
    """Test HMAC signature validation."""
    
    def test_missing_signature_returns_401(self, client):
        """Test that missing X-Signature header returns 401."""
        payload = create_valid_message()
        response = client.post(
            "/webhook",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}
    
    def test_invalid_signature_returns_401(self, client, webhook_secret):
        """Test that invalid signature returns 401."""
        payload = create_valid_message()
        response = client.post(
            "/webhook",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Signature": "invalid-signature"
            }
        )
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid signature"}
    
    def test_valid_signature_accepted(self, client, webhook_secret):
        """Test that valid signature is accepted."""
        payload = create_valid_message()
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_signature_uses_raw_body(self, client, webhook_secret):
        """Test that signature is computed from raw body bytes."""
        # Different JSON formatting should produce different signatures
        payload = {"message_id": "m1", "from": "+1234567890", "to": "+0987654321", "ts": "2025-01-15T10:00:00Z"}
        
        # Compact JSON
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 200


class TestWebhookValidation:
    """Test payload validation."""
    
    def test_missing_message_id_returns_422(self, client, webhook_secret):
        """Test that missing message_id returns 422."""
        payload = {"from": "+1234567890", "to": "+0987654321", "ts": "2025-01-15T10:00:00Z"}
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_empty_message_id_returns_422(self, client, webhook_secret):
        """Test that empty message_id returns 422."""
        payload = create_valid_message(message_id="")
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_invalid_from_format_returns_422(self, client, webhook_secret):
        """Test that invalid E.164 format for 'from' returns 422."""
        payload = create_valid_message(from_number="1234567890")  # Missing +
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_invalid_to_format_returns_422(self, client, webhook_secret):
        """Test that invalid E.164 format for 'to' returns 422."""
        payload = create_valid_message(to_number="invalid")
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_invalid_timestamp_format_returns_422(self, client, webhook_secret):
        """Test that invalid timestamp format returns 422."""
        payload = create_valid_message(ts="2025-01-15 10:00:00")  # Missing T and Z
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_timestamp_without_z_returns_422(self, client, webhook_secret):
        """Test that timestamp without Z suffix returns 422."""
        payload = create_valid_message(ts="2025-01-15T10:00:00+00:00")
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_text_max_length_4096(self, client, webhook_secret):
        """Test that text field respects max length of 4096."""
        # Text within limit should be accepted
        payload = create_valid_message(text="a" * 4096)
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 200
    
    def test_text_exceeds_max_length_returns_422(self, client, webhook_secret):
        """Test that text exceeding 4096 chars returns 422."""
        payload = create_valid_message(text="a" * 4097)
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 422
    
    def test_optional_text_field(self, client, webhook_secret):
        """Test that text field is optional."""
        payload = {"message_id": "m1", "from": "+1234567890", "to": "+0987654321", "ts": "2025-01-15T10:00:00Z"}
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 200


class TestWebhookIdempotency:
    """Test idempotent message insertion."""
    
    def test_new_message_inserted(self, client, webhook_secret):
        """Test that new message is inserted successfully."""
        payload = create_valid_message(message_id="new-msg-1")
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        response = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        
        # Verify message was inserted
        messages_response = client.get("/messages")
        assert messages_response.status_code == 200
        assert messages_response.json()["total"] == 1
    
    def test_duplicate_message_returns_200(self, client, webhook_secret):
        """Test that duplicate message_id returns 200 without error."""
        payload = create_valid_message(message_id="dup-msg-1")
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        # First insertion
        response1 = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response1.status_code == 200
        
        # Duplicate insertion
        response2 = client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        assert response2.status_code == 200
        assert response2.json() == {"status": "ok"}
    
    def test_duplicate_does_not_insert_new_row(self, client, webhook_secret):
        """Test that duplicate message_id does not create a new row."""
        payload = create_valid_message(message_id="dup-msg-2")
        body = json.dumps(payload).encode("utf-8")
        signature = compute_signature(webhook_secret, body)
        
        # First insertion
        client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        
        # Get count after first insertion
        messages1 = client.get("/messages")
        count1 = messages1.json()["total"]
        
        # Duplicate insertion
        client.post(
            "/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature
            }
        )
        
        # Get count after duplicate
        messages2 = client.get("/messages")
        count2 = messages2.json()["total"]
        
        # Count should not increase
        assert count1 == count2
    
    def test_invalid_signature_no_db_insert(self, client, webhook_secret):
        """Test that invalid signature does not insert into DB."""
        payload = create_valid_message(message_id="invalid-sig-msg")
        
        # Send with invalid signature
        client.post(
            "/webhook",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-Signature": "invalid"
            }
        )
        
        # Verify no message was inserted
        messages_response = client.get("/messages")
        assert messages_response.json()["total"] == 0
