from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List
import subprocess
import os
from pathlib import Path
from typing import Optional

import crontab_utils

router = APIRouter(prefix="/api/cron-jobs", tags=["Cron Jobs"])

class CronJobBase(BaseModel):
    schedule: str
    command: str
    enabled: bool
    comment: str = ""
    valid: bool
    has_logging: bool
    log_path: str = ""  # Add this line

class CronJobCreate(CronJobBase):
    pass

class CronJobUpdate(CronJobBase):
    index: int

@router.get("/", response_model=List[CronJobBase])
def list_cron_jobs():
    return crontab_utils.get_crontab()

@router.post("/")
def add_cron_job(job: CronJobCreate):
    try:
        crontab_utils.add_cron_job(job.dict())
        return {"status": "added"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/")
def update_cron_job(job: CronJobUpdate):
    try:
        crontab_utils.update_cron_job(job.index, job.dict())
        return {"status": "updated"}
    except IndexError:
        raise HTTPException(status_code=404, detail="Invalid index")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{index}")
def delete_cron_job(index: int):
    try:
        crontab_utils.remove_cron_job(index)
        return {"status": "deleted"}
    except IndexError:
        raise HTTPException(status_code=404, detail="Invalid index")

@router.get("/logs")
def get_logs(path: str = Query(..., description="Full path to the log file"), 
             lines: Optional[int] = Query(None, description="Number of lines to return")):
    try:
        # Validate that the path exists and is a file
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        
        if not os.path.isfile(path):
            raise HTTPException(status_code=400, detail=f"Path is not a file: {path}")
        
        # Security check - resolve the path
        resolved_path = Path(path).resolve()
        
        # Optional: Restrict to specific directories for security
        # allowed_dirs = [Path("/home/pi"), Path("/var/log")]
        # if not any(str(resolved_path).startswith(str(allowed_dir)) for allowed_dir in allowed_dirs):
        #     raise HTTPException(status_code=403, detail="Access to this directory is not allowed")
        
        # Build the tail command
        cmd = ["tail"]
        if lines is not None and lines > 0:
            cmd.extend(["-n", str(lines)])
        cmd.append(str(resolved_path))
        
        # Execute the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=30  # Add timeout to prevent hanging
        )
        
        return {
            "success": True,
            "path": str(resolved_path),
            "lines_requested": lines,
            "log": result.stdout
        }
        
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error reading file: {e.stderr if e.stderr else str(e)}"
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Request timeout while reading file")
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied to read file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")