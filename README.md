# FastAPI Webhook Service

A production-grade containerized FastAPI service that ingests WhatsApp-like messages with HMAC signature validation, stores them in SQLite with idempotency, and provides multiple API endpoints for message retrieval, analytics, health checks, and metrics.

## Setup Used

- **IDE**: VSCode with GitHub Copilot
- **Framework**: FastAPI (Python async framework)
- **Database**: SQLite (file-based)
- **Containerization**: Docker + Docker Compose

## Prerequisites

- Docker
- Docker Compose
- Make (optional, for convenience commands)
- curl (for testing endpoints)
- jq (optional, for pretty-printing JSON)

## Quick Start

1. **Clone the repository** and navigate to the project directory.

2. **Set the required environment variable**:
   ```bash
   export WEBHOOK_SECRET="your-secret-here"
   ```

3. **Start the service**:
   ```bash
   make up
   ```

4. **Verify the service is running**:
   ```bash
   curl http://localhost:8000/health/live
   curl http://localhost:8000/health/ready
   ```

5. **Stop the service**:
   ```bash
   make down
   ```

## API Endpoints

### POST /webhook

Ingest messages with HMAC signature validation.

**Headers**:
- `Content-Type: application/json`
- `X-Signature: <hex HMAC-SHA256 of raw request body>`

**Example**:
```bash
# Generate signature
SECRET="your-secret-here"
BODY='{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello"}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

# Send request
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
```

**Response**: `{"status": "ok"}`

### GET /messages

List stored messages with pagination and filters.

**Query Parameters**:
- `limit` (optional, 1-100, default 50)
- `offset` (optional, default 0)
- `from` (optional): Filter by sender
- `since` (optional): Filter by timestamp (ISO-8601)
- `q` (optional): Text search (case-insensitive)

**Example**:
```bash
# List all messages
curl "http://localhost:8000/messages"

# With pagination
curl "http://localhost:8000/messages?limit=10&offset=0"

# Filter by sender
curl "http://localhost:8000/messages?from=%2B919876543210"

# Filter by timestamp
curl "http://localhost:8000/messages?since=2025-01-15T00:00:00Z"

# Text search
curl "http://localhost:8000/messages?q=hello"
```

### GET /stats

Get message analytics.

**Example**:
```bash
curl http://localhost:8000/stats
```

**Response**:
```json
{
  "total_messages": 123,
  "senders_count": 10,
  "messages_per_sender": [
    {"from": "+919876543210", "count": 50},
    {"from": "+911234567890", "count": 30}
  ],
  "first_message_ts": "2025-01-10T09:00:00Z",
  "last_message_ts": "2025-01-15T10:00:00Z"
}
```

### GET /health/live

Liveness probe - always returns 200 when the process is running.

```bash
curl http://localhost:8000/health/live
```

### GET /health/ready

Readiness probe - returns 200 only when:
- Database is reachable
- Schema is applied
- WEBHOOK_SECRET is configured

```bash
curl http://localhost:8000/health/ready
```

### GET /metrics

Prometheus-style metrics exposition.

```bash
curl http://localhost:8000/metrics
```

## Design Decisions

### HMAC Verification

- Uses raw request body bytes for signature computation (before JSON parsing)
- Implements `hmac.compare_digest()` for timing-safe comparison
- Returns 401 with generic "invalid signature" message (no information leakage)
- Verification happens before any payload validation or database operations

### Pagination Contract

- Default limit: 50, configurable between 1-100
- Offset-based pagination (simple and predictable)
- Deterministic ordering: `ORDER BY ts ASC, message_id ASC`
- `total` always returns count of ALL matching rows (ignoring limit/offset)

### Stats Calculation

- `total_messages`: Simple `COUNT(*)` on messages table
- `senders_count`: `COUNT(DISTINCT from_msisdn)`
- `messages_per_sender`: Top 10 senders via `GROUP BY` + `ORDER BY count DESC`
- Timestamps: `MIN(ts)` and `MAX(ts)` queries (returns null if no messages)

### Idempotency

- Primary key constraint on `message_id` prevents duplicates
- Catches `sqlite3.IntegrityError` gracefully
- Returns 200 for both new and duplicate messages
- No error information exposed for duplicate handling

### Metrics Implementation

Uses `prometheus_client` library with:
- HTTP request counter with path and status labels
- Webhook outcome counter (created, duplicate, invalid_signature, validation_error)
- Request latency histogram with standard buckets

### Structured Logging

- One JSON object per log line
- Includes: timestamp, level, request_id, method, path, status, latency_ms
- Webhook-specific fields: message_id, dup, result
- All timestamps in ISO-8601 UTC format

## Testing

### Run Tests Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
make test
```

### Manual Testing Script

```bash
#!/bin/bash
SECRET="test-secret-123"

# Test 1: Health checks
echo "=== Testing Health Endpoints ==="
curl -s http://localhost:8000/health/live | jq .
curl -s http://localhost:8000/health/ready | jq .

# Test 2: Invalid signature
echo "=== Testing Invalid Signature ==="
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: invalid" \
  -d '{"message_id":"m1","from":"+1234567890","to":"+0987654321","ts":"2025-01-15T10:00:00Z"}' | jq .

# Test 3: Valid message
echo "=== Testing Valid Message ==="
BODY='{"message_id":"m1","from":"+1234567890","to":"+0987654321","ts":"2025-01-15T10:00:00Z","text":"Hello"}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIG" \
  -d "$BODY" | jq .

# Test 4: Duplicate message
echo "=== Testing Duplicate Message ==="
curl -s -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIG" \
  -d "$BODY" | jq .

# Test 5: Get messages
echo "=== Testing GET /messages ==="
curl -s "http://localhost:8000/messages" | jq .

# Test 6: Get stats
echo "=== Testing GET /stats ==="
curl -s http://localhost:8000/stats | jq .

# Test 7: Metrics
echo "=== Testing GET /metrics ==="
curl -s http://localhost:8000/metrics
```

## Project Structure

```
/app
  - main.py           # FastAPI app, middleware, routes
  - models.py         # SQLite initialization and schema
  - storage.py        # Database operations (CRUD)
  - logging_utils.py  # JSON logger setup
  - metrics.py        # Prometheus metrics helpers
  - config.py         # Environment variable loading
/tests
  - test_webhook.py   # Test webhook validation, signatures, duplicates
  - test_messages.py  # Test pagination and filters
  - test_stats.py     # Test stats endpoint correctness
Dockerfile            # Multi-stage build
docker-compose.yml    # Service orchestration
Makefile             # Common commands
README.md            # This file
.env.example         # Example environment variables
.gitignore           # Ignore DB files, __pycache__, etc.
```

## Troubleshooting

### Service won't start

1. **Check WEBHOOK_SECRET is set**:
   ```bash
   echo $WEBHOOK_SECRET
   ```

2. **Check Docker logs**:
   ```bash
   make logs
   ```

### 401 Unauthorized on webhook

1. Ensure the signature is computed correctly using HMAC-SHA256
2. Use the exact raw body bytes for signature computation
3. Verify the secret matches between client and server

### Database errors

1. **Check volume permissions**:
   ```bash
   docker compose exec api ls -la /data
   ```

2. **Reset the database**:
   ```bash
   make down  # This removes volumes
   make up
   ```

### Logs not appearing

1. Check LOG_LEVEL environment variable
2. Use `make logs` to tail container logs
3. Logs are JSON format - use `jq` to parse:
   ```bash
   docker compose logs api | jq -R 'fromjson? // empty'
   ```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| WEBHOOK_SECRET | Yes | - | Secret key for HMAC signature validation |
| DATABASE_URL | No | sqlite:////data/app.db | SQLite connection string |
| LOG_LEVEL | No | INFO | Logging level (INFO, DEBUG) |

## License

MIT
