import fcntl
import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator, List

from crontab import CRON_COMMAND, CronTab

import storage

_THREAD_CRONTAB_LOCK = threading.RLock()


@contextmanager
def crontab_lock() -> Iterator[None]:
    """Serialize app crontab operations across threads and worker processes."""
    with _THREAD_CRONTAB_LOCK:
        database_path = storage.database_path()
        lock_path = database_path.with_name(database_path.name + ".crontab.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class CrontabSnapshot:
    content: bytes
    exists: bool

    def display_text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def get_crontab_snapshot() -> CrontabSnapshot:
    """Read exact crontab bytes without parsing or rendering them."""
    result = subprocess.run(
        [CRON_COMMAND, "-l"],
        capture_output=True,
        check=False,
        timeout=15,
    )
    if result.returncode == 0:
        return CrontabSnapshot(result.stdout, True)
    stderr = result.stderr.decode("utf-8", errors="replace")
    if "no crontab for" in stderr.lower():
        return CrontabSnapshot(b"", False)
    raise RuntimeError(f"Could not read current crontab: {stderr.strip()}")


def install_crontab_snapshot(snapshot: CrontabSnapshot) -> None:
    """Restore exact snapshot bytes directly through crontab(1)."""
    if snapshot.exists:
        result = subprocess.run(
            [CRON_COMMAND, "-"],
            input=snapshot.content,
            capture_output=True,
            check=False,
            timeout=15,
        )
    else:
        result = subprocess.run(
            [CRON_COMMAND, "-r"],
            capture_output=True,
            check=False,
            timeout=15,
        )
        if (
            result.returncode
            and "no crontab for"
            in result.stderr.decode("utf-8", errors="replace").lower()
        ):
            return
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Could not restore crontab snapshot: {stderr.strip()}")


def validate_command(command: str) -> None:
    """Basic command validation to prevent obvious issues."""
    dangerous_patterns = [
        r"rm\s+-rf\s+/",  # Recursive delete from root
        r":\(\)\{.*\|.*&.*\};:",  # Fork bomb
        r"mkfs\.",  # Filesystem formatting
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            raise ValueError(
                f"Command contains potentially dangerous pattern: {pattern}"
            )


def get_crontab() -> List[dict]:
    """Return the user's crontab as job dictionaries."""
    cron = CronTab(user=True)
    jobs = []
    for job in cron:
        command = str(job.command)
        # Always convert @hourly/@monthly/etc to classic cron syntax for frontend
        schedule = convert_special_schedules(str(job.slices))
        jobs.append(
            {
                "schedule": schedule,
                "command": command,
                "enabled": bool(job.is_enabled()),
                "comment": str(job.comment),
                "valid": bool(job.is_valid()),
                "has_logging": any(
                    pattern in command for pattern in [">> ", "> ", "2>&1", "2> "]
                ),
                "log_path": extract_log_path(command),
            }
        )
    return jobs


def add_cron_job(job_data: Dict) -> None:
    """Adds a new cron job from structured data, with validation."""
    validate_command(job_data["command"])
    cron = CronTab(user=True)
    schedule = convert_special_schedules(job_data["schedule"])
    job = cron.new(command=job_data["command"], comment=job_data["comment"])
    job.setall(schedule)
    if not job.is_valid():
        raise ValueError("Invalid cron schedule")
    if not job_data["enabled"]:
        job.enable(False)
    cron.write()


def remove_cron_job(index: int) -> None:
    """Removes a line from the crontab by index."""
    cron = CronTab(user=True)
    jobs = list(cron)
    if 0 <= index < len(jobs):
        cron.remove(jobs[index])
        cron.write()
    else:
        raise IndexError("Invalid cron job index.")


def update_cron_job(index: int, job_data: Dict) -> None:
    """Update a cron job in place, preserving its position and validating input."""
    cron = CronTab(user=True)
    jobs = list(cron)
    if not (0 <= index < len(jobs)):
        raise IndexError("Invalid cron job index")
    job = jobs[index]
    validate_command(job_data["command"])
    schedule = convert_special_schedules(job_data["schedule"])
    job.set_command(job_data["command"])
    job.set_comment(job_data["comment"])
    job.setall(schedule)
    if not job.is_valid():
        raise ValueError("Invalid cron schedule")
    job.enable(job_data["enabled"])
    # CronTab writes via crontab(1), which installs the prepared full text.
    # The audit layer records exact bytes before/after and leaves the before
    # snapshot available if a failed write needs operator recovery.
    cron.write()


def duplicate_cron_job(index: int) -> None:
    """Duplicates an existing cron job by index."""
    cron = CronTab(user=True)
    jobs = list(cron)
    if 0 <= index < len(jobs):
        job = jobs[index]
        new_job = cron.new(command=job.command, comment=job.comment)
        new_job.setall(job.slices)
        new_job.enable(False)  # Set duplicated job as inactive
        cron.write()
    else:
        raise IndexError("Invalid cron job index.")


# Improved log path extraction to catch more patterns
def extract_log_path(command: str) -> str:
    # Try to match common logging patterns
    # 1. > file.log, >> file.log, 2> file.log, 2>&1 file.log, &> file.log
    patterns = [r"(?:>>|>|2>|2>&1|&>)\s*([^\s]+\.log)", r"tee\s+([^\s]+\.log)"]
    for pat in patterns:
        match = re.search(pat, command)
        if match:
            return match.group(1)
    return ""


def get_crontab_text() -> str:
    """Returns current crontab text without re-rendering parsed cron entries."""
    return get_crontab_snapshot().display_text()


def import_cron_jobs(jobs: List[Dict]) -> None:
    """Imports cron jobs from a list of dictionaries."""
    cron = CronTab(user=True)
    for job_data in jobs:
        schedule = convert_special_schedules(job_data["schedule"])
        job = cron.new(command=job_data["command"], comment=job_data.get("comment", ""))
        job.setall(schedule)
        if not job.is_valid():
            raise ValueError(f"Invalid cron schedule: {schedule}")
        if not job_data.get("enabled", True):
            job.enable(False)
    cron.write()


# Helper to convert @hourly/@monthly to classic cron syntax
def convert_special_schedules(schedule: str) -> str:
    mapping = {
        "@hourly": "0 * * * *",
        "@monthly": "0 0 1 * *",
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
    }
    return mapping.get(schedule.strip(), schedule)
