from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

import crontab_utils

router = APIRouter(prefix="/api/cron-jobs", tags=["Cron Jobs"])

class CronJobBase(BaseModel):
    schedule: str
    command: str
    enabled: bool
    comment: str = ""
    valid: bool
    has_logging: bool

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
