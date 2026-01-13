"""
Structured JSON logging utilities.
Produces one JSON object per line for log aggregation.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON log records."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_data: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "path"):
            log_data["path"] = record.path
        if hasattr(record, "status"):
            log_data["status"] = record.status
        if hasattr(record, "latency_ms"):
            log_data["latency_ms"] = record.latency_ms
        if hasattr(record, "message_id"):
            log_data["message_id"] = record.message_id
        if hasattr(record, "dup"):
            log_data["dup"] = record.dup
        if hasattr(record, "result"):
            log_data["result"] = record.result
        
        # Include exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(name: str = "app", level: str = "INFO") -> logging.Logger:
    """
    Set up a JSON logger.
    
    Args:
        name: Logger name
        level: Log level (INFO, DEBUG, etc.)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Set level
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Create handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


class RequestLogger:
    """Helper class to log request information in a structured way."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        status: int,
        latency_ms: float,
        message_id: Optional[str] = None,
        dup: Optional[bool] = None,
        result: Optional[str] = None,
        level: str = "INFO"
    ) -> None:
        """
        Log a request with all required fields.
        
        Args:
            request_id: Unique request identifier
            method: HTTP method
            path: Request path
            status: HTTP status code
            latency_ms: Request duration in milliseconds
            message_id: Message ID (for webhook requests)
            dup: Whether this was a duplicate (for webhook requests)
            result: Result type (for webhook requests)
            level: Log level
        """
        extra: Dict[str, Any] = {
            "request_id": request_id,
            "method": method,
            "path": path,
            "status": status,
            "latency_ms": round(latency_ms, 2),
        }
        
        if message_id is not None:
            extra["message_id"] = message_id
        if dup is not None:
            extra["dup"] = dup
        if result is not None:
            extra["result"] = result
        
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method("request completed", extra=extra)


# Global logger instance
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get the global logger instance, creating it if necessary."""
    global _logger
    if _logger is None:
        from .config import get_settings
        settings = get_settings()
        _logger = setup_logger("app", settings.log_level)
    return _logger
