from fastapi import APIRouter, Query

import cron_log_monitor
import storage

router = APIRouter(prefix="/api/execution-history", tags=["Execution History"])


@router.get("")
def get_execution_history(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    # Opportunistically ingest recent host log records when the configured log is
    # mounted/readable; monitoring failures never prevent reading history.
    monitoring = cron_log_monitor.ingest_configured_cron_log()
    return {
        "monitoring": monitoring,
        "items": storage.list_execution_history(limit=limit, offset=offset),
        "limit": limit,
        "offset": offset,
        "semantics": {
            "event_type": "launch_observed",
            "outcome": "unknown",
            "note": (
                "Cron logs show that a command was launched, not whether it "
                "completed successfully."
            ),
        },
    }
