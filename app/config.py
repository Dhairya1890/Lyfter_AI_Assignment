"""
Configuration module for loading environment variables.
Follows 12-factor app principles.
"""
import os
from functools import lru_cache
from typing import Optional


class Settings:
    """Application settings loaded from environment variables."""
    
    def __init__(self) -> None:
        self.webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    @property
    def database_path(self) -> str:
        """Extract the file path from the SQLite connection string."""
        # Format: sqlite:////path/to/file.db
        if self.database_url.startswith("sqlite:///"):
            return self.database_url.replace("sqlite:///", "")
        return "/data/app.db"
    
    def validate(self) -> bool:
        """Validate that all required settings are present."""
        return bool(self.webhook_secret)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
