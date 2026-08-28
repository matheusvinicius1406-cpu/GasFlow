import os
from pydantic import BaseModel
from typing import List


class Settings(BaseModel):
    app_name: str = "GasFlow"
    app_version: str = "0.1.0"
    
    # CORS
    cors_origins: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]
    cors_methods: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    cors_headers: List[str] = ["Authorization", "Content-Type", "Accept"]
    
    @classmethod
    def from_env(cls):
        """Load settings from environment variables."""
        origins_str = os.getenv("CORS_ORIGINS", "")
        origins = [o.strip() for o in origins_str.split(",") if o.strip()] if origins_str else None
        return cls(
            cors_origins=origins if origins else cls.model_fields["cors_origins"].default,
        )


settings = Settings.from_env()