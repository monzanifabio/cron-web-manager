from crontab import CronTab
from typing import List, Dict
import re

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
    """Writes a new crontab from a list of lines."""
    cron = CronTab(user=True)
    cron.remove_all()
    for line in lines:
        if line.strip():  # Skip empty lines
            cron.new(command=line)
    cron.write()

def add_cron_job(job_data: Dict) -> None:
    """Adds a new cron job from structured data."""
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
    """Updates an existing cron job with structured data."""
    cron = CronTab(user=True)
    jobs = list(cron)
    
    if 0 <= index < len(jobs):
        old_job = jobs[index]
        cron.remove(old_job)
        
        job = cron.new(command=job_data["command"], comment=job_data["comment"])
        job.setall(job_data["schedule"])
        
        if not job.is_valid():
            # Restore the old job if the new one is invalid
            cron.new(command=old_job.command, comment=old_job.comment)
            raise ValueError("Invalid cron schedule")
        
        if not job_data["enabled"]:
            job.enable(False)
        
        cron.write()
    else:
        raise IndexError("Invalid cron job index")

# Example: extract log path from command (very basic)
def extract_log_path(command: str) -> str:
    # Match '>> /path/to/log.log' or '> /path/to/log.log', but not '2>' or '2>&1'
    match = re.search(r'(?:>>|>)\s+([^\s]+\.log)', command)
    return match.group(1) if match else ""
