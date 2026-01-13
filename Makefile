.PHONY: up down logs test clean build

# Start the service
up:
	docker compose up -d --build

# Stop the service and remove volumes
down:
	docker compose down -v

# View logs
logs:
	docker compose logs -f api

# Run tests locally
test:
	WEBHOOK_SECRET=test-secret DATABASE_URL=sqlite:///./test.db pytest tests/ -v

# Clean up test artifacts
clean:
	rm -f test.db
	rm -rf __pycache__
	rm -rf app/__pycache__
	rm -rf tests/__pycache__
	rm -rf .pytest_cache

# Build without starting
build:
	docker compose build

# Rebuild from scratch
rebuild:
	docker compose build --no-cache

# Check service health
health:
	curl -s http://localhost:8000/health/live | jq .
	curl -s http://localhost:8000/health/ready | jq .
