import shutil
import tempfile
def validate_command(command: str) -> None:
    """Basic command validation to prevent obvious issues."""
    dangerous_patterns = [
        r'rm\s+-rf\s+/',  # Recursive delete from root
        r':\(\)\{.*\|.*&.*\};:',  # Fork bomb
        r'mkfs\.',  # Filesystem formatting
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, command):
            raise ValueError(f"Command contains potentially dangerous pattern: {pattern}")
from crontab import CronTab
from typing import List, Dict
import re
import os

def get_crontab() -> List[dict]:
    """Returns the current user's crontab as a list of dictionaries containing job details."""
    cron = CronTab(user=True)
    jobs = []
    for job in cron:
        command = str(job.command)
        jobs.append({
            'schedule': str(job.slices),
            'command': command,
            'enabled': bool(job.is_enabled()),
            'comment': str(job.comment),
            'valid': bool(job.is_valid()),
            'has_logging': any(pattern in command for pattern in ['>> ', '> ', '2>&1', '2> ']),
            'log_path': extract_log_path(command)
        })
    return jobs

def write_crontab(lines: List[str]) -> None:
    """Writes a new crontab from a list of lines, with backup and rollback."""
    cron = CronTab(user=True)
    # Backup current crontab
    backup_fd, backup_path = tempfile.mkstemp(prefix="crontab_backup_")
    try:
        with open(backup_path, "w") as backup_file:
            backup_file.write(str(cron))
        cron.remove_all()
        for line in lines:
            if line.strip():  # Skip empty lines
                cron.new(command=line)
        cron.write()
    except Exception as e:
        # Rollback on failure
        with open(backup_path, "r") as backup_file:
            cron = CronTab(tab=backup_file.read(), user=True)
            cron.write()
        raise RuntimeError(f"Failed to write crontab, rolled back. Error: {e}")
    finally:
        try:
            os.close(backup_fd)
            os.remove(backup_path)
        except Exception:
            pass

def add_cron_job(job_data: Dict) -> None:
    """Adds a new cron job from structured data, with validation."""
    validate_command(job_data["command"])
    cron = CronTab(user=True)
    job = cron.new(command=job_data["command"], comment=job_data["comment"])
    job.setall(job_data["schedule"])
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
    """Updates an existing cron job while preserving its position and with validation."""
    cron = CronTab(user=True)
    jobs = list(cron)
    if not (0 <= index < len(jobs)):
        raise IndexError("Invalid cron job index")
    job = jobs[index]
    validate_command(job_data["command"])
    # Backup current crontab
    backup_fd, backup_path = tempfile.mkstemp(prefix="crontab_backup_")
    try:
        with open(backup_path, "w") as backup_file:
            backup_file.write(str(cron))
        job.set_command(job_data["command"])
        job.set_comment(job_data["comment"])
        job.setall(job_data["schedule"])
        if not job.is_valid():
            raise ValueError("Invalid cron schedule")
        job.enable(job_data["enabled"])
        cron.write()
    except Exception as e:
        # Rollback on failure
        with open(backup_path, "r") as backup_file:
            cron = CronTab(tab=backup_file.read(), user=True)
            cron.write()
        raise RuntimeError(f"Failed to update cron job, rolled back. Error: {e}")
    finally:
        try:
            os.close(backup_fd)
            os.remove(backup_path)
        except Exception:
            pass

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
    patterns = [
        r'(?:>>|>|2>|2>&1|&>)\s*([^\s]+\.log)',
        r'tee\s+([^\s]+\.log)'
    ]
    for pat in patterns:
        match = re.search(pat, command)
        if match:
            return match.group(1)
    return ""

def import_cron_jobs(jobs: List[Dict]) -> None:
    """Imports cron jobs from a list of dictionaries."""
    cron = CronTab(user=True)
    for job_data in jobs:
        job = cron.new(command=job_data["command"], comment=job_data.get("comment", ""))
        job.setall(job_data["schedule"])
        if not job.is_valid():
            raise ValueError(f"Invalid cron schedule: {job_data['schedule']}")
        if not job_data.get("enabled", True):
            job.enable(False)
    cron.write()
