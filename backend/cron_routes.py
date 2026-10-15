import os
import subprocess
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import crontab_utils
from crontab_audit import audited_change

router = APIRouter(prefix="/api/cron-jobs", tags=["Cron Jobs"])

class CronJobInput(BaseModel):
    schedule: str
    command: str
    enabled: bool
    comment: str = ""

class CronJobCreate(CronJobInput):
    pass

class CronJobUpdate(CronJobInput):
    index: int

class CronJobBase(BaseModel):
    schedule: str
    command: str
    enabled: bool
    comment: str = ""
    valid: bool
    has_logging: bool
    log_path: str = ""

# List jobs
@router.get("")
def list_cron_jobs():
    return crontab_utils.get_crontab()

# Add job
@router.post("")
def add_cron_job(job: CronJobCreate):
    try:
        _, change_id = audited_change(
            "add",
            f"Add {job.comment or job.schedule}",
            lambda: crontab_utils.add_cron_job(job.model_dump()),
        )
        return {"status": "added", "change_id": change_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Update job
@router.put("")
def update_cron_job(job: CronJobUpdate):
    try:
        _, change_id = audited_change(
            "update",
            f"Update crontab entry {job.index}",
            lambda: crontab_utils.update_cron_job(job.index, job.model_dump()),
        )
        return {"status": "updated", "change_id": change_id}
    except IndexError:
        raise HTTPException(status_code=404, detail="Invalid index")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Delete job
@router.delete("/{index}")
def delete_cron_job(index: int):
    try:
        _, change_id = audited_change(
            "delete",
            f"Delete crontab entry {index}",
            lambda: crontab_utils.remove_cron_job(index),
        )
        return {"status": "deleted", "change_id": change_id}
    except IndexError:
        raise HTTPException(status_code=404, detail="Invalid index")

# Get logs
@router.get("/logs")
def get_logs(
    path: str = Query(..., description="Full path to the log file"),
    lines: Optional[int] = Query(None, description="Number of lines to return")
):
    try:
        # SECURITY: Validate the path is actually from a cron job
        current_jobs = crontab_utils.get_crontab()
        valid_log_paths = {job['log_path'] for job in current_jobs if job['log_path']}
        if path not in valid_log_paths:
            raise HTTPException(
                status_code=403,
                detail="Can only read log files from configured cron jobs"
            )
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        if not os.path.isfile(path):
            raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")
        resolved_path = Path(path).resolve()
        cmd = ["tail"]
        if lines is not None and lines > 0:
            cmd.extend(["-n", str(lines)])
        cmd.append(str(resolved_path))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )
        return {
            "success": True,
            "path": str(resolved_path),
            "lines_requested": lines,
            "log": result.stdout
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e.stderr if e.stderr else str(e)}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Request timeout while reading file")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied to read file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

# Duplicate job
@router.post("/{index}/duplicate")
def duplicate_cron_job(index: int):
    try:
        _, change_id = audited_change(
            "duplicate",
            f"Duplicate crontab entry {index}",
            lambda: crontab_utils.duplicate_cron_job(index),
        )
        return {"status": "duplicated", "change_id": change_id}
    except IndexError:
        raise HTTPException(status_code=404, detail="Invalid index")

# Export jobs
@router.get("/export")
def export_cron_jobs():
    """Endpoint to export all cron jobs to a JSON file."""
    return crontab_utils.get_crontab()


@router.get("/raw")
def export_raw_crontab():
    """Endpoint to return the full raw crontab text."""
    return {"crontab": crontab_utils.get_crontab_text()}

class CronJobImport(BaseModel):
    jobs: List[CronJobInput]

# Import jobs
@router.post("/import")
def import_cron_jobs(payload: CronJobImport):
    """Endpoint to import cron jobs from a JSON file."""
    try:
        jobs_to_import = [job.model_dump() for job in payload.jobs]
        _, change_id = audited_change(
            "import",
            f"Import {len(jobs_to_import)} cron job(s)",
            lambda: crontab_utils.import_cron_jobs(jobs_to_import),
        )
        return {"status": "imported", "change_id": change_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
