"""Best-effort ingestion of explicitly configured host cron logs.

Cron log records are launch observations only. They contain no reliable exit
status, so stored execution outcomes always remain ``unknown``.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import storage

logger = logging.getLogger(__name__)

_CRON_CMD_RE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+"
    r"(?P<clock>\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+"
    r"(?P<daemon>CRON|CROND)\[(?P<pid>\d+)\]:\s+"
    r"\((?P<user>[^)]+)\)\s+CMD\s+\((?P<command>.*)\)\s*$"
)
_JOURNAL_CMD_RE = re.compile(r"^\((?P<user>[^)]+)\)\s+CMD\s+\((?P<command>.*)\)$")
_JOURNAL_CURSOR_RE = re.compile(r"^-- cursor: (.+)$")
_ingest_lock = threading.Lock()
_state_lock = threading.Lock()
_monitor_state: dict[str, Any] = {
    "enabled": False,
    "available": False,
    "path": None,
    "last_read_at": None,
    "error": "CRON_LOG_PATH is not configured",
}


def _set_state(**updates: Any) -> None:
    with _state_lock:
        _monitor_state.update(updates)


def monitoring_status() -> dict[str, Any]:
    path = os.environ.get("CRON_LOG_PATH", "").strip()
    if not path:
        return {
            "enabled": False,
            "available": False,
            "path": None,
            "last_read_at": None,
            "error": "CRON_LOG_PATH is not configured",
        }
    with _state_lock:
        status = dict(_monitor_state)
    if status.get("path") != path:
        return {
            "enabled": True,
            "available": False,
            "path": path,
            "last_read_at": None,
            "error": "Configured cron log has not been checked yet",
        }
    status["enabled"] = True
    return status


def _parse_syslog_time(month: str, day: str, clock: str, file_mtime: float) -> str:
    mtime_year = datetime.fromtimestamp(file_mtime).year
    candidates = []
    for year in (mtime_year - 1, mtime_year, mtime_year + 1):
        try:
            candidates.append(datetime.strptime(
                f"{year} {month} {int(day)} {clock}", "%Y %b %d %H:%M:%S"
            ).astimezone())
        except ValueError:
            continue
    if not candidates:
        raise ValueError(f"Invalid cron log timestamp: {month} {day} {clock}")
    closest = min(
        candidates,
        key=lambda candidate: abs(candidate.timestamp() - file_mtime),
    )
    return closest.astimezone(timezone.utc).isoformat()


def _parse_command_log_line(line: str, file_mtime: float) -> dict[str, Any] | None:
    match = _CRON_CMD_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    values = match.groupdict()
    try:
        observed_at = _parse_syslog_time(
            values["month"], values["day"], values["clock"], file_mtime
        )
    except ValueError:
        return None
    return {
        "observed_at": observed_at,
        "username": values["user"],
        "process_id": int(values["pid"]),
        "command": values["command"],
    }


def _journalctl_output(
    path: Path, cursor: str | None
) -> subprocess.CompletedProcess[str]:
    command = [
        "journalctl",
        f"--directory={path}",
        "--unit=cron",
        "--output=json",
        "--no-pager",
        "--show-cursor",
    ]
    if cursor:
        command.append(f"--after-cursor={cursor}")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode and cursor:
        # Journal rotation/vacuuming can invalidate the saved cursor. Re-read
        # retained records; event cursors make replay idempotent.
        command = [
            argument
            for argument in command
            if not argument.startswith("--after-cursor=")
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    if result.returncode:
        detail = result.stderr.strip() or f"journalctl exited {result.returncode}"
        raise OSError(detail)
    return result


def _ingest_systemd_journal(path: Path, configured_path: str) -> dict[str, Any]:
    journal_files = list(path.rglob("*.journal"))
    if not journal_files:
        raise OSError("configured directory contains no readable systemd journal files")
    # Probe a journal file directly so unreadable bind mounts are reported rather
    # than appearing as a healthy source with no events.
    with journal_files[0].open("rb"):
        pass

    with _ingest_lock:
        resolved_path = str(path.resolve())
        with storage.connect() as connection:
            row = connection.execute(
                "SELECT journal_cursor FROM journal_log_cursors WHERE source_path = ?",
                (resolved_path,),
            ).fetchone()
        saved_cursor = row["journal_cursor"] if row else None
        output = _journalctl_output(path, saved_cursor)

        new_cursor = saved_cursor
        events = []
        for line in output.stdout.splitlines():
            cursor_match = _JOURNAL_CURSOR_RE.match(line)
            if cursor_match:
                new_cursor = cursor_match.group(1)
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message_match = _JOURNAL_CMD_RE.match(str(entry.get("MESSAGE", "")))
            entry_cursor = entry.get("__CURSOR")
            if (
                message_match is None
                or entry.get("SYSLOG_IDENTIFIER") not in {"CRON", "CROND"}
                or not entry_cursor
            ):
                continue
            try:
                observed_at = datetime.fromtimestamp(
                    int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000,
                    tz=timezone.utc,
                ).isoformat()
                process_id = int(entry.get("SYSLOG_PID", entry.get("_PID")))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            events.append(
                {
                    "cursor": str(entry_cursor),
                    "observed_at": observed_at,
                    "username": message_match.group("user"),
                    "process_id": process_id,
                    "command": message_match.group("command"),
                }
            )

        read_at = datetime.now(timezone.utc).isoformat()
        inserted_count = 0
        with storage.connect() as connection:
            for event in events:
                event_key = hashlib.sha256(
                    f"{resolved_path}\\0{event['cursor']}".encode()
                ).hexdigest()
                result = connection.execute(
                    """
                    INSERT OR IGNORE INTO execution_history
                        (event_key, observed_at, event_type, outcome, username,
                         process_id, command, source_path, source_offset)
                    VALUES (?, ?, 'launch_observed', 'unknown', ?, ?, ?, ?, 0)
                    """,
                    (
                        event_key,
                        event["observed_at"],
                        event["username"],
                        event["process_id"],
                        event["command"],
                        resolved_path,
                    ),
                )
                inserted_count += result.rowcount
            if new_cursor:
                connection.execute(
                    """
                    INSERT INTO journal_log_cursors
                        (source_path, journal_cursor, last_read_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(source_path) DO UPDATE SET
                        journal_cursor = excluded.journal_cursor,
                        last_read_at = excluded.last_read_at
                    """,
                    (resolved_path, new_cursor, read_at),
                )

    _set_state(
        enabled=True,
        available=True,
        path=configured_path,
        last_read_at=read_at,
        error=None,
    )
    return {**monitoring_status(), "new_events": inserted_count}


def ingest_configured_cron_log() -> dict[str, Any]:
    """Read newly appended cron CMD records and persist launch observations.

    A missing/unreadable optional host log is reported as monitor status, not an
    application error, and never affects crontab CRUD operations.
    """
    configured_path = os.environ.get("CRON_LOG_PATH", "").strip()
    if not configured_path:
        _set_state(
            enabled=False,
            available=False,
            path=None,
            error="CRON_LOG_PATH is not configured",
        )
        return monitoring_status()

    path = Path(configured_path).expanduser()
    try:
        if path.is_dir():
            return _ingest_systemd_journal(path, configured_path)
        if not path.is_file():
            raise OSError("configured path is not a regular file or journal directory")
        with _ingest_lock:
            with path.open("rb") as source:
                stat = os.fstat(source.fileno())
                resolved_path = str(path.resolve())
                with storage.connect() as connection:
                    cursor = connection.execute(
                        """
                        SELECT device, inode, byte_offset FROM cron_log_cursors
                        WHERE source_path = ?
                        """,
                        (resolved_path,),
                    ).fetchone()
                    if (
                        cursor is None
                        or cursor["device"] != stat.st_dev
                        or cursor["inode"] != stat.st_ino
                        or stat.st_size < cursor["byte_offset"]
                    ):
                        start_offset = 0
                    else:
                        start_offset = cursor["byte_offset"]

                    source.seek(start_offset)
                    chunk = source.read(1024 * 1024)
                    complete_length = len(chunk)
                    if chunk and not chunk.endswith(b"\n"):
                        final_newline = chunk.rfind(b"\n")
                        complete_length = final_newline + 1 if final_newline >= 0 else 0
                    complete_chunk = chunk[:complete_length]
                    byte_offset = start_offset
                    inserted_count = 0
                    for raw_line in complete_chunk.splitlines(keepends=True):
                        line_offset = byte_offset
                        byte_offset += len(raw_line)
                        line = raw_line.decode("utf-8", errors="replace")
                        event = _parse_command_log_line(line, stat.st_mtime)
                        if event is None:
                            continue
                        event_key = hashlib.sha256(
                            f"{resolved_path}\0{stat.st_dev}\0{stat.st_ino}\0{line_offset}\0".encode()
                            + raw_line
                        ).hexdigest()
                        result = connection.execute(
                            """
                            INSERT OR IGNORE INTO execution_history
                                (event_key, observed_at, event_type, outcome, username,
                                 process_id, command, source_path, source_offset)
                            VALUES (?, ?, 'launch_observed', 'unknown', ?, ?, ?, ?, ?)
                            """,
                            (
                                event_key,
                                event["observed_at"],
                                event["username"],
                                event["process_id"],
                                event["command"],
                                resolved_path,
                                line_offset,
                            ),
                        )
                        inserted_count += result.rowcount

                    read_at = datetime.now(timezone.utc).isoformat()
                    connection.execute(
                        """
                        INSERT INTO cron_log_cursors
                            (source_path, device, inode, byte_offset, last_read_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(source_path) DO UPDATE SET
                            device = excluded.device,
                            inode = excluded.inode,
                            byte_offset = excluded.byte_offset,
                            last_read_at = excluded.last_read_at
                        """,
                        (resolved_path, stat.st_dev, stat.st_ino, byte_offset, read_at),
                    )
        _set_state(
            enabled=True,
            available=True,
            path=configured_path,
            last_read_at=read_at,
            error=None,
        )
        return {**monitoring_status(), "new_events": inserted_count}
    except OSError as exc:
        message = f"Cannot read configured cron log: {exc.strerror or str(exc)}"
        _set_state(
            enabled=True,
            available=False,
            path=configured_path,
            last_read_at=None,
            error=message,
        )
        logger.warning("Cron log monitoring unavailable: %s", message)
        return monitoring_status()


async def monitor_loop() -> None:
    try:
        interval = max(1.0, float(os.environ.get("CRON_LOG_POLL_SECONDS", "10")))
    except ValueError:
        interval = 10.0
    while True:
        try:
            await asyncio.to_thread(ingest_configured_cron_log)
        except Exception:
            logger.exception(
                "Cron log ingestion failed; API and crontab management will continue"
            )
        await asyncio.sleep(interval)
