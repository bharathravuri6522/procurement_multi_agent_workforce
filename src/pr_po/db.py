"""Database connection helpers for the PR-to-PO subsystem."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config import settings


DB_PATH = Path(settings.database_path)
DEFAULT_TIMEOUT_SECONDS = 30.0


def get_connection() -> sqlite3.Connection:
    """Return a configured SQLite connection with row and FK support."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DB_PATH,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA busy_timeout = 30000;")
    return connection
