"""SQLite storage for application settings and observed cron-log events.

Scheduled job definitions intentionally remain in the user's crontab.
"""

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def database_path() -> Path:
    configured_path = os.environ.get("DATABASE_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path(__file__).resolve().parent / "data" / "cron-web-manager.sqlite3"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );

            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                observed_at TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type = 'launch_observed'),
                outcome TEXT NOT NULL CHECK (outcome = 'unknown'),
                username TEXT NOT NULL,
                process_id INTEGER NOT NULL,
                command TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_offset INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_execution_history_observed_at
                ON execution_history(observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_execution_history_command
                ON execution_history(command);

            CREATE TABLE IF NOT EXISTS cron_log_cursors (
                source_path TEXT PRIMARY KEY,
                device INTEGER NOT NULL,
                inode INTEGER NOT NULL,
                byte_offset INTEGER NOT NULL,
                last_read_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journal_log_cursors (
                source_path TEXT PRIMARY KEY,
                journal_cursor TEXT NOT NULL,
                last_read_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS crontab_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT NOT NULL,
                summary TEXT NOT NULL,
                related_change_id INTEGER,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                outcome TEXT NOT NULL CHECK (
                    outcome IN ('pending', 'succeeded', 'failed', 'unknown')
                ),
                error TEXT,
                before_snapshot BLOB,
                before_exists INTEGER,
                before_sha256 TEXT,
                after_snapshot BLOB,
                after_exists INTEGER,
                after_sha256 TEXT,
                after_snapshot_source TEXT,
                FOREIGN KEY (related_change_id) REFERENCES crontab_changes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_crontab_changes_started_at
                ON crontab_changes(started_at DESC);
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(crontab_changes)")
        }
        if "after_snapshot_source" not in columns:
            connection.execute(
                "ALTER TABLE crontab_changes ADD COLUMN after_snapshot_source TEXT"
            )


def get_settings() -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT key, value_json, updated_at FROM app_settings ORDER BY key"
        ).fetchall()
    return {
        row["key"]: {
            "value": json.loads(row["value_json"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


def set_setting(key: str, value: Any) -> None:
    value_json = json.dumps(value, ensure_ascii=False, allow_nan=False)
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO app_settings (key, value_json) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (key, value_json),
        )


def delete_setting(key: str) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    return cursor.rowcount > 0


def list_execution_history(limit: int, offset: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, observed_at, event_type, outcome, username, process_id,
                   command, source_path
            FROM execution_history
            ORDER BY observed_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def snapshot_sha256(snapshot: bytes | None, exists: bool | None) -> str | None:
    if snapshot is None or exists is None:
        return None
    presence = b"\x01" if exists else b"\x00"
    return hashlib.sha256(presence + snapshot).hexdigest()


def begin_crontab_change(
    operation: str,
    summary: str,
    before_snapshot: bytes | None,
    before_exists: bool | None,
    related_change_id: int | None = None,
) -> int:
    started_at = datetime.now(timezone.utc).isoformat()
    before_sha256 = snapshot_sha256(before_snapshot, before_exists)
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO crontab_changes
                (operation, summary, related_change_id, started_at, outcome,
                 before_snapshot, before_exists, before_sha256)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                operation,
                summary,
                related_change_id,
                started_at,
                before_snapshot,
                None if before_exists is None else int(before_exists),
                before_sha256,
            ),
        )
        return int(cursor.lastrowid)


def finish_crontab_change(
    change_id: int,
    *,
    after_snapshot: bytes | None,
    after_exists: bool | None,
    outcome: str,
    error: str | None = None,
    after_snapshot_source: str = "operation",
) -> None:
    if outcome not in {"succeeded", "failed", "unknown"}:
        raise ValueError(f"Unsupported crontab change outcome: {outcome}")
    if after_snapshot_source not in {
        "operation",
        "recovery_observation",
        "unavailable",
    }:
        raise ValueError("Unsupported after-snapshot source")
    completed_at = datetime.now(timezone.utc).isoformat()
    after_sha256 = snapshot_sha256(after_snapshot, after_exists)
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE crontab_changes SET
                completed_at = ?, outcome = ?, error = ?, after_snapshot = ?,
                after_exists = ?, after_sha256 = ?, after_snapshot_source = ?
            WHERE id = ? AND outcome = 'pending'
            """,
            (
                completed_at,
                outcome,
                error[:2000] if error else None,
                after_snapshot,
                None if after_exists is None else int(after_exists),
                after_sha256,
                after_snapshot_source,
                change_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Pending crontab change {change_id} was not found")


def reconcile_pending_crontab_changes(
    after_snapshot: bytes | None,
    after_exists: bool | None,
    error: str,
) -> int:
    """Close interrupted records as unknown with the current observed state."""
    completed_at = datetime.now(timezone.utc).isoformat()
    after_sha256 = snapshot_sha256(after_snapshot, after_exists)
    source = (
        "recovery_observation"
        if after_snapshot is not None and after_exists is not None
        else "unavailable"
    )
    with connect() as connection:
        cursor = connection.execute(
            """
            UPDATE crontab_changes SET
                completed_at = ?, outcome = 'unknown', error = ?,
                after_snapshot = ?, after_exists = ?, after_sha256 = ?,
                after_snapshot_source = ?
            WHERE outcome = 'pending'
            """,
            (
                completed_at,
                error[:2000],
                after_snapshot,
                None if after_exists is None else int(after_exists),
                after_sha256,
                source,
            ),
        )
        return cursor.rowcount


def list_pending_crontab_changes() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM crontab_changes WHERE outcome = 'pending' ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def list_crontab_changes(limit: int, offset: int) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, operation, summary, related_change_id, started_at,
                   completed_at, outcome, error, before_sha256, after_sha256,
                   before_exists, after_exists, after_snapshot_source
            FROM crontab_changes
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(row) for row in rows]


def get_crontab_change(change_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM crontab_changes WHERE id = ?", (change_id,)
        ).fetchone()
    return None if row is None else dict(row)
