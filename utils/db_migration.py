# utils/db_migration.py
# Version 1.0.0
"""
SQLite schema migration runner for the Discord bot.

CREATED v1.0.0: Schema extension & enhanced capture (SOW v3.1.0)
- Replaces inline SCHEMA_SQL in message_store.py with versioned SQL files
- Scans schema/ directory for NNN.sql files in sequential order
- Applies unapplied migrations and records each in schema_version table
- Idempotent: safe to run against both new and existing databases

Called from init_database() in message_store.py after connection setup.
Schema files live in schema/ at the project root. Each file is a
self-contained migration that must be safe to run in sequence.
"""
import os
import re
from datetime import datetime, timezone

from utils.logging_utils import get_logger

logger = get_logger('db_migration')

# schema/ directory is at the project root (two levels above utils/)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(_PROJECT_ROOT, 'schema')


def run_migrations(conn):
    """
    Apply all unapplied migrations from schema/ to the database.

    Creates schema_version table if needed, scans for NNN.sql files,
    and executes any not yet recorded. Each migration is committed
    atomically with its version record. Running against an already-
    current database is a no-op.

    Args:
        conn: sqlite3.Connection — must be open and writable
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    conn.commit()

    applied = {row[0] for row in conn.execute(
        "SELECT version FROM schema_version"
    ).fetchall()}

    migrations = _load_migration_files()

    for version, path in migrations:
        if version in applied:
            logger.debug(f"Migration {version:03d} already applied, skipping")
            continue

        logger.info(f"Applying migration {version:03d}: {os.path.basename(path)}")
        with open(path, 'r') as f:
            sql = f.read()

        conn.executescript(sql)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (version, now)
        )
        conn.commit()
        logger.info(f"Migration {version:03d} applied successfully")

    logger.debug(
        f"Migration check complete. {len(migrations)} files scanned, "
        f"{len(applied)} previously applied"
    )


def _load_migration_files():
    """
    Scan schema/ for NNN.sql files and return sorted (version, path) pairs.

    Returns:
        list[tuple[int, str]]: Sorted by version number ascending
    """
    if not os.path.isdir(SCHEMA_DIR):
        logger.warning(f"Schema directory not found: {SCHEMA_DIR}")
        return []

    pattern = re.compile(r'^(\d{3})\.sql$')
    migrations = []
    for filename in os.listdir(SCHEMA_DIR):
        match = pattern.match(filename)
        if match:
            version = int(match.group(1))
            migrations.append((version, os.path.join(SCHEMA_DIR, filename)))

    migrations.sort(key=lambda x: x[0])
    return migrations
