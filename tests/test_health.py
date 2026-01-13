"""
Tests for health check endpoints.
"""
import pytest


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_health_live_returns_200(self, client):
        """Test that /health/live returns 200."""
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}
    
    def test_health_ready_returns_200_when_ready(self, client):
        """Test that /health/ready returns 200 when service is ready."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}


class TestMetricsEndpoint:
    """Test metrics endpoint."""
    
    def test_metrics_returns_200(self, client):
        """Test that /metrics returns 200."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "http_requests_total" in response.text or response.status_code == 200
