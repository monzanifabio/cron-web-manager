from collections.abc import Callable
from typing import Any

import crontab_utils
import storage


def recover_pending_changes() -> int:
    """Capture live state for interrupted records without inferring outcomes."""
    with crontab_utils.crontab_lock():
        if not storage.list_pending_crontab_changes():
            return 0
        try:
            observed = crontab_utils.get_crontab_snapshot()
        except Exception as exc:
            return storage.reconcile_pending_crontab_changes(
                None,
                None,
                "Process restarted before outcome commit; current crontab "
                f"could not be captured during recovery: {exc}",
            )
        return storage.reconcile_pending_crontab_changes(
            observed.content,
            observed.exists,
            "Process restarted before outcome commit; after snapshot is the "
            "exact current crontab observed during recovery. Outcome remains unknown.",
        )


def audited_change(
    operation: str,
    summary: str,
    action: Callable[[], Any],
    related_change_id: int | None = None,
) -> tuple[Any, int]:
    """Run an app mutation with durable exact before/after crontab snapshots."""
    with crontab_utils.crontab_lock():
        try:
            before = crontab_utils.get_crontab_snapshot()
        except Exception as exc:
            change_id = storage.begin_crontab_change(
                operation,
                summary,
                before_snapshot=None,
                before_exists=None,
                related_change_id=related_change_id,
            )
            storage.finish_crontab_change(
                change_id,
                after_snapshot=None,
                after_exists=None,
                outcome="failed",
                error=f"Could not capture before snapshot: {exc}",
                after_snapshot_source="unavailable",
            )
            raise

        change_id = storage.begin_crontab_change(
            operation,
            summary,
            before_snapshot=before.content,
            before_exists=before.exists,
            related_change_id=related_change_id,
        )
        try:
            result = action()
        except Exception as action_error:
            try:
                after = crontab_utils.get_crontab_snapshot()
            except Exception as snapshot_error:
                storage.finish_crontab_change(
                    change_id,
                    after_snapshot=None,
                    after_exists=None,
                    outcome="unknown",
                    error=(
                        f"{action_error}; after snapshot unavailable: {snapshot_error}"
                    ),
                    after_snapshot_source="unavailable",
                )
            else:
                storage.finish_crontab_change(
                    change_id,
                    after_snapshot=after.content,
                    after_exists=after.exists,
                    outcome="failed",
                    error=str(action_error),
                )
            raise

        try:
            after = crontab_utils.get_crontab_snapshot()
        except Exception as snapshot_error:
            storage.finish_crontab_change(
                change_id,
                after_snapshot=None,
                after_exists=None,
                outcome="unknown",
                error=(
                    f"Action returned but after snapshot unavailable: {snapshot_error}"
                ),
                after_snapshot_source="unavailable",
            )
            raise
        storage.finish_crontab_change(
            change_id,
            after_snapshot=after.content,
            after_exists=after.exists,
            outcome="succeeded",
        )
        return result, change_id
