import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import storage

router = APIRouter(prefix="/api/settings", tags=["Application Settings"])
_SETTING_KEY_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")


class SettingValue(BaseModel):
    value: Any


def validate_key(key: str) -> str:
    if not _SETTING_KEY_RE.fullmatch(key):
        raise HTTPException(
            status_code=400,
            detail=(
                "Setting keys may contain only letters, numbers, periods, "
                "underscores, and hyphens (max 100 characters)"
            ),
        )
    return key


@router.get("")
def list_settings():
    return {"settings": storage.get_settings()}


@router.put("/{key}")
def save_setting(key: str, request: SettingValue):
    validate_key(key)
    try:
        json.dumps(request.value, allow_nan=False)
        storage.set_setting(key, request.value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Setting value must be JSON serializable: {exc}",
        )
    return {"key": key, "value": request.value}


@router.delete("/{key}")
def remove_setting(key: str):
    validate_key(key)
    if not storage.delete_setting(key):
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"status": "deleted", "key": key}
