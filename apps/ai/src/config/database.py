"""Centralized database configuration — env-only, no hardcoded credentials."""
from __future__ import annotations

import os


def get_database_url(default_db: str = "iterateswarm") -> str:
    """Get database URL from environment. Never fall back to hardcoded credentials.

    Checks DATABASE_URL first, then composes from DB_USER/DB_PASSWORD/DB_PORT.
    This ensures any existing production deployments with DATABASE_URL set
    continue to work unchanged.

    Args:
        default_db: Default database name if none specified in env

    Returns:
        Database URL from env or a safe localhost default with no hardcoded credentials
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("DB_USER", "iterateswarm")
    password = os.environ.get("DB_PASSWORD", "")  # require explicit env
    port = os.environ.get("DB_PORT", "5432")
    if not password:
        return f"postgresql://{user}@localhost:{port}/{default_db}?sslmode=disable"
    return f"postgresql://{user}:{password}@localhost:{port}/{default_db}"

