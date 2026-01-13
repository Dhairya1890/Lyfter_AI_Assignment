"""
Prometheus metrics helpers.
Provides counters and histograms for monitoring.
"""
from prometheus_client import Counter, Histogram, REGISTRY, generate_latest
from typing import Optional


# HTTP request counter with path and status labels
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["path", "status"]
)

# Webhook-specific outcome counter
webhook_requests_total = Counter(
    "webhook_requests_total",
    "Total webhook requests by result",
    ["result"]
)

# Request latency histogram with buckets
request_latency_ms = Histogram(
    "request_latency_ms",
    "Request latency in milliseconds",
    ["path"],
    buckets=[10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")]
)


def record_request(path: str, status: int, latency_ms: float) -> None:
    """
    Record an HTTP request for metrics.
    
    Args:
        path: Request path
        status: HTTP status code
        latency_ms: Request latency in milliseconds
    """
    http_requests_total.labels(path=path, status=str(status)).inc()
    request_latency_ms.labels(path=path).observe(latency_ms)


def record_webhook_result(result: str) -> None:
    """
    Record a webhook processing result.
    
    Args:
        result: One of "created", "duplicate", "invalid_signature", "validation_error"
    """
    webhook_requests_total.labels(result=result).inc()


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.
    
    Returns:
        Prometheus metrics as bytes
    """
    return generate_latest(REGISTRY)
