"""
FastAPI webhook service main application.
Handles WhatsApp-like message ingestion with HMAC validation.
"""
import hmac
import hashlib
import time
import uuid
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Annotated

from fastapi import FastAPI, Request, Response, HTTPException, Query, Header
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from .config import get_settings
from .models import init_db, check_db_ready
from .storage import MessageStorage
from .logging_utils import get_logger, RequestLogger
from .metrics import record_request, record_webhook_result, get_metrics


# E.164 phone number regex: starts with + followed by digits only
E164_PATTERN = re.compile(r"^\+[0-9]+$")

# ISO-8601 UTC regex: must end with Z
ISO8601_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


class WebhookPayload(BaseModel):
    """Pydantic model for webhook request validation."""
    
    message_id: str = Field(..., min_length=1, description="Unique message identifier")
    from_: str = Field(..., alias="from", description="Sender phone number in E.164 format")
    to: str = Field(..., description="Recipient phone number in E.164 format")
    ts: str = Field(..., description="Timestamp in ISO-8601 UTC format with Z suffix")
    text: Optional[str] = Field(None, max_length=4096, description="Message text")
    
    @field_validator("from_", mode="before")
    @classmethod
    def validate_from_e164(cls, v: str) -> str:
        """Validate from field is in E.164 format."""
        if not E164_PATTERN.match(v):
            raise ValueError("Invalid E.164 format: must start with + followed by digits")
        return v
    
    @field_validator("to")
    @classmethod
    def validate_to_e164(cls, v: str) -> str:
        """Validate to field is in E.164 format."""
        if not E164_PATTERN.match(v):
            raise ValueError("Invalid E.164 format: must start with + followed by digits")
        return v
    
    @field_validator("ts")
    @classmethod
    def validate_ts_iso8601(cls, v: str) -> str:
        """Validate ts field is ISO-8601 UTC format ending with Z."""
        if not ISO8601_UTC_PATTERN.match(v):
            raise ValueError("Invalid ISO-8601 UTC format: must end with Z")
        # Also verify it's a valid datetime
        try:
            # Python's fromisoformat doesn't handle 'Z' directly, replace with +00:00
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid datetime value")
        return v
    
    class Config:
        populate_by_name = True


class WebhookResponse(BaseModel):
    """Response model for webhook endpoint."""
    status: str = "ok"


class MessageListResponse(BaseModel):
    """Response model for message listing."""
    data: list
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    """Response model for stats endpoint."""
    total_messages: int
    senders_count: int
    messages_per_sender: list
    first_message_ts: Optional[str]
    last_message_ts: Optional[str]


# Request state storage for middleware
class RequestState:
    """Store request-specific state."""
    request_id: str
    start_time: float
    webhook_message_id: Optional[str] = None
    webhook_dup: Optional[bool] = None
    webhook_result: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - startup and shutdown."""
    settings = get_settings()
    
    # Validate required settings on startup
    if not settings.validate():
        raise RuntimeError("WEBHOOK_SECRET environment variable is required")
    
    # Initialize database
    init_db()
    
    logger = get_logger()
    logger.info("Application started")
    
    yield
    
    logger.info("Application shutting down")


app = FastAPI(
    title="Webhook Service",
    description="WhatsApp-like message ingestion service with HMAC validation",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Middleware to log all requests with structured JSON logging.
    Generates request_id, tracks latency, and logs all required fields.
    """
    # Generate unique request ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    request.state.start_time = time.time()
    request.state.webhook_message_id = None
    request.state.webhook_dup = None
    request.state.webhook_result = None
    
    # Process request
    response = await call_next(request)
    
    # Calculate latency
    latency_ms = (time.time() - request.state.start_time) * 1000
    
    # Get logger and log the request
    logger = get_logger()
    request_logger = RequestLogger(logger)
    
    # Determine log level based on status code
    level = "INFO" if response.status_code < 400 else "ERROR"
    
    # Build log entry
    request_logger.log_request(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=latency_ms,
        message_id=getattr(request.state, "webhook_message_id", None),
        dup=getattr(request.state, "webhook_dup", None),
        result=getattr(request.state, "webhook_result", None),
        level=level
    )
    
    # Record metrics
    record_request(request.url.path, response.status_code, latency_ms)
    
    return response


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """
    Verify HMAC-SHA256 signature.
    
    Args:
        secret: The secret key for HMAC
        body: Raw request body bytes
        signature: Hex-encoded signature from header
    
    Returns:
        True if signature is valid, False otherwise
    """
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


@app.post("/webhook", response_model=WebhookResponse)
async def webhook(
    request: Request,
    x_signature: Annotated[Optional[str], Header(alias="X-Signature")] = None
):
    """
    Ingest messages with HMAC signature validation.
    
    - Validates HMAC-SHA256 signature
    - Validates payload format
    - Ensures idempotent message storage
    """
    settings = get_settings()
    
    # Get raw body for HMAC verification (before JSON parsing)
    body = await request.body()
    
    # Verify signature
    if not x_signature:
        request.state.webhook_result = "invalid_signature"
        record_webhook_result("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid signature")
    
    if not verify_signature(settings.webhook_secret, body, x_signature):
        request.state.webhook_result = "invalid_signature"
        record_webhook_result("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid signature")
    
    # Parse and validate payload
    try:
        import json
        payload_data = json.loads(body)
        payload = WebhookPayload(**payload_data)
    except Exception as e:
        request.state.webhook_result = "validation_error"
        record_webhook_result("validation_error")
        raise HTTPException(status_code=422, detail=str(e))
    
    # Store request state for logging
    request.state.webhook_message_id = payload.message_id
    
    # Insert message (handles duplicates via database constraint)
    success, is_duplicate = MessageStorage.insert_message(
        message_id=payload.message_id,
        from_msisdn=payload.from_,
        to_msisdn=payload.to,
        ts=payload.ts,
        text=payload.text
    )
    
    request.state.webhook_dup = is_duplicate
    
    if is_duplicate:
        request.state.webhook_result = "duplicate"
        record_webhook_result("duplicate")
    else:
        request.state.webhook_result = "created"
        record_webhook_result("created")
    
    return WebhookResponse(status="ok")


@app.get("/messages", response_model=MessageListResponse)
async def get_messages(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    from_: Annotated[Optional[str], Query(alias="from")] = None,
    since: Optional[str] = None,
    q: Optional[str] = None
):
    """
    List stored messages with pagination and filters.
    
    - Supports pagination with limit/offset
    - Filter by sender (from), timestamp (since), or text search (q)
    - Returns total count of matching messages
    """
    result = MessageStorage.get_messages(
        limit=limit,
        offset=offset,
        from_filter=from_,
        since=since,
        q=q
    )
    
    return result


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get message analytics.
    
    Returns:
    - Total message count
    - Unique sender count
    - Top 10 senders by message count
    - First and last message timestamps
    """
    return MessageStorage.get_stats()


@app.get("/health/live")
async def health_live():
    """
    Liveness probe - indicates the process is running.
    Always returns 200 once the app is running.
    """
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    """
    Readiness probe - indicates the app is ready to receive traffic.
    
    Checks:
    - Database is reachable
    - Database schema is applied
    - WEBHOOK_SECRET is configured
    """
    settings = get_settings()
    
    # Check WEBHOOK_SECRET is set
    if not settings.validate():
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "WEBHOOK_SECRET not configured"}
        )
    
    # Check database is ready
    if not check_db_ready():
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "Database not ready"}
        )
    
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    return Response(
        content=get_metrics(),
        media_type="text/plain; charset=utf-8"
    )


# Custom exception handler to prevent stack traces in responses
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions without exposing stack traces."""
    logger = get_logger()
    logger.error(f"Unhandled exception: {type(exc).__name__}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )
