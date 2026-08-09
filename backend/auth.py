import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(_API_KEY_HEADER)) -> None:
    """Dependency that enforces API key auth when API_KEY env var is set.

    If API_KEY is not configured the check is skipped, allowing unauthenticated
    access during local development.
    """
    expected = os.environ.get("API_KEY")
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
