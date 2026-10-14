from difflib import diff_bytes, unified_diff

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import crontab_utils
import storage

router = APIRouter(prefix="/api/crontab-history", tags=["Crontab History"])


class RollbackRequest(BaseModel):
    expected_current_sha256: str = Field(min_length=64, max_length=64)


def _snapshot_diff(
    before: bytes, after: bytes, after_label: bytes = b"after crontab"
) -> str:
    diff = diff_bytes(
        unified_diff,
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=b"before crontab",
        tofile=after_label,
    )
    return b"".join(diff).decode("utf-8", errors="replace")


def _require_change(change_id: int) -> dict:
    change = storage.get_crontab_change(change_id)
    if change is None:
        raise HTTPException(status_code=404, detail="Crontab change not found")
    return change


def _public_change(change: dict, include_snapshots: bool = False) -> dict:
    public = {
        key: change[key]
        for key in (
            "id",
            "operation",
            "summary",
            "related_change_id",
            "started_at",
            "completed_at",
            "outcome",
            "error",
            "before_sha256",
            "after_sha256",
            "before_exists",
            "after_exists",
            "after_snapshot_source",
        )
    }
    if include_snapshots:
        before = change["before_snapshot"]
        after = change["after_snapshot"]
        public.update(
            before_text=None
            if before is None
            else bytes(before).decode("utf-8", errors="replace"),
            after_text=None
            if after is None
            else bytes(after).decode("utf-8", errors="replace"),
            diff=(
                None
                if before is None or after is None
                else _snapshot_diff(
                    bytes(before),
                    bytes(after),
                    after_label=(
                        b"crontab observed during recovery"
                        if change["after_snapshot_source"] == "recovery_observation"
                        else b"after crontab"
                    ),
                )
            ),
        )
    return public


@router.get("")
def list_crontab_history(limit: int = 100, offset: int = 0):
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(
            status_code=422, detail="limit must be 1–200 and offset non-negative"
        )
    return {
        "items": [
            _public_change(item) for item in storage.list_crontab_changes(limit, offset)
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/{change_id}")
def get_crontab_history(change_id: int):
    return _public_change(_require_change(change_id), include_snapshots=True)


@router.get("/{change_id}/rollback-preview")
def preview_rollback(change_id: int):
    change = _require_change(change_id)
    before = change["before_snapshot"]
    after = change["after_snapshot"]
    if (
        before is None
        or after is None
        or change["before_exists"] is None
        or change["after_exists"] is None
    ):
        return {
            "change_id": change_id,
            "can_rollback": False,
            "stale": False,
            "reason": "This history entry does not contain complete snapshots.",
            "diff": None,
        }

    with crontab_utils.crontab_lock():
        try:
            current = crontab_utils.get_crontab_snapshot()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"Could not verify current crontab: {exc}"
            )

    current_hash = storage.snapshot_sha256(current.content, current.exists)
    recorded_after_hash = change["after_sha256"]
    stale = current_hash != recorded_after_hash
    has_change = bytes(before) != bytes(after) or bool(change["before_exists"]) != bool(
        change["after_exists"]
    )
    can_rollback = not stale and has_change and change["outcome"] != "pending"
    return {
        "change_id": change_id,
        "can_rollback": can_rollback,
        "stale": stale,
        "reason": (
            "Current crontab differs from this change's after snapshot; "
            "refusing to overwrite newer state."
            if stale
            else "No crontab content change to restore."
            if not has_change
            else None
        ),
        "expected_current_sha256": current_hash,
        "recorded_after_sha256": recorded_after_hash,
        "current_exists": current.exists,
        "target_exists": bool(change["before_exists"]),
        "diff": _snapshot_diff(current.content, bytes(before)),
    }


@router.post("/{change_id}/rollback")
def rollback_crontab_change(change_id: int, request: RollbackRequest):
    change = _require_change(change_id)
    before = change["before_snapshot"]
    after = change["after_snapshot"]
    if (
        before is None
        or after is None
        or change["before_exists"] is None
        or change["after_exists"] is None
    ):
        raise HTTPException(
            status_code=409, detail="This history entry has no restorable snapshot"
        )
    if change["outcome"] == "pending":
        raise HTTPException(
            status_code=409, detail="Cannot roll back an unfinished change"
        )

    with crontab_utils.crontab_lock():
        try:
            current = crontab_utils.get_crontab_snapshot()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"Could not verify current crontab: {exc}"
            )
        current_hash = storage.snapshot_sha256(current.content, current.exists)
        if (
            current_hash != request.expected_current_sha256
            or current_hash != change["after_sha256"]
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Crontab changed since the rollback preview; "
                    "refresh history and preview again."
                ),
            )
        if current.content == bytes(before) and current.exists == bool(
            change["before_exists"]
        ):
            raise HTTPException(
                status_code=409, detail="Crontab already matches the restore target"
            )

        rollback_id = storage.begin_crontab_change(
            "rollback",
            f"Restore crontab to before change {change_id}",
            before_snapshot=current.content,
            before_exists=current.exists,
            related_change_id=change_id,
        )
        target = crontab_utils.CrontabSnapshot(
            content=bytes(before),
            exists=bool(change["before_exists"]),
        )
        try:
            crontab_utils.install_crontab_snapshot(target)
        except Exception as exc:
            try:
                failed_after = crontab_utils.get_crontab_snapshot()
            except Exception as snapshot_error:
                storage.finish_crontab_change(
                    rollback_id,
                    after_snapshot=None,
                    after_exists=None,
                    outcome="unknown",
                    error=f"{exc}; after snapshot unavailable: {snapshot_error}",
                    after_snapshot_source="unavailable",
                )
            else:
                storage.finish_crontab_change(
                    rollback_id,
                    after_snapshot=failed_after.content,
                    after_exists=failed_after.exists,
                    outcome="failed",
                    error=str(exc),
                )
            raise HTTPException(
                status_code=500, detail=f"Crontab restore failed: {exc}"
            )

        try:
            restored = crontab_utils.get_crontab_snapshot()
        except Exception as exc:
            storage.finish_crontab_change(
                rollback_id,
                after_snapshot=None,
                after_exists=None,
                outcome="unknown",
                error=f"Restore command completed but verification failed: {exc}",
                after_snapshot_source="unavailable",
            )
            raise HTTPException(
                status_code=500, detail="Restored crontab could not be verified"
            )

        if restored.content != target.content or restored.exists != target.exists:
            storage.finish_crontab_change(
                rollback_id,
                after_snapshot=restored.content,
                after_exists=restored.exists,
                outcome="failed",
                error="Installed crontab did not exactly match the snapshot.",
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Restore command completed, but exact snapshot verification failed."
                ),
            )
        storage.finish_crontab_change(
            rollback_id,
            after_snapshot=restored.content,
            after_exists=restored.exists,
            outcome="succeeded",
        )
    return {
        "status": "rolled_back",
        "change_id": rollback_id,
        "restored_from": change_id,
    }
