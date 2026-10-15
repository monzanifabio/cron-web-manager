import multiprocessing
import os
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import crontab_utils  # noqa: E402
import storage  # noqa: E402
from crontab_audit import (
    audited_change,  # noqa: E402
    recover_pending_changes,  # noqa: E402
)
from main import app  # noqa: E402

client = TestClient(app)
read_exact_crontab_snapshot = crontab_utils.get_crontab_snapshot
install_exact_crontab_snapshot = crontab_utils.install_crontab_snapshot


def _hold_crontab_lock(held, release):
    with crontab_utils.crontab_lock():
        held.set()
        release.wait(timeout=5)


def _wait_for_crontab_lock(attempted, acquired):
    attempted.set()
    with crontab_utils.crontab_lock():
        acquired.set()


def test_crontab_lock_serializes_separate_worker_processes():
    context = multiprocessing.get_context("fork")
    held = context.Event()
    release = context.Event()
    attempted = context.Event()
    acquired = context.Event()
    first = context.Process(target=_hold_crontab_lock, args=(held, release))
    second = context.Process(target=_wait_for_crontab_lock, args=(attempted, acquired))

    first.start()
    assert held.wait(timeout=3)
    second.start()
    assert attempted.wait(timeout=3)
    assert not acquired.wait(timeout=0.2)
    release.set()
    assert acquired.wait(timeout=3)
    first.join(timeout=3)
    second.join(timeout=3)
    assert first.exitcode == 0
    assert second.exitcode == 0


def test_exact_snapshot_reads_crontab_bytes_and_absent_state(monkeypatch):
    outputs = iter(
        [
            subprocess.CompletedProcess(
                args=["crontab", "-l"],
                returncode=0,
                stdout=b"MAILTO=x@example.test\r\n# note\r\n\r\n",
                stderr=b"",
            ),
            subprocess.CompletedProcess(
                args=["crontab", "-l"],
                returncode=0,
                stdout=b"",
                stderr=b"",
            ),
            subprocess.CompletedProcess(
                args=["crontab", "-l"],
                returncode=1,
                stdout=b"",
                stderr=b"no crontab for test-user",
            ),
        ]
    )
    run = Mock(side_effect=lambda *_args, **_kwargs: next(outputs))
    monkeypatch.setattr(crontab_utils.subprocess, "run", run)
    monkeypatch.setattr(
        crontab_utils, "get_crontab_snapshot", read_exact_crontab_snapshot
    )

    present = crontab_utils.get_crontab_snapshot()
    empty = crontab_utils.get_crontab_snapshot()
    absent = crontab_utils.get_crontab_snapshot()

    assert present.content == b"MAILTO=x@example.test\r\n# note\r\n\r\n"
    assert present.exists is True
    assert empty.content == b""
    assert empty.exists is True
    assert absent.content == b""
    assert absent.exists is False
    assert storage.snapshot_sha256(
        empty.content, empty.exists
    ) != storage.snapshot_sha256(absent.content, absent.exists)
    assert run.call_args_list[0].args[0] == [crontab_utils.CRON_COMMAND, "-l"]


def test_snapshot_restore_passes_original_bytes_directly_to_crontab(monkeypatch):
    original = b"SHELL=/bin/sh\\r\\n# keep formatting\\r\\n\\r\\n"
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=[crontab_utils.CRON_COMMAND, "-"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )
    )
    monkeypatch.setattr(crontab_utils.subprocess, "run", run)
    monkeypatch.setattr(
        crontab_utils, "install_crontab_snapshot", install_exact_crontab_snapshot
    )

    crontab_utils.install_crontab_snapshot(
        crontab_utils.CrontabSnapshot(original, True)
    )

    run.assert_called_once_with(
        [crontab_utils.CRON_COMMAND, "-"],
        input=original,
        capture_output=True,
        check=False,
        timeout=15,
    )


def test_restore_of_missing_snapshot_removes_crontab(monkeypatch):
    run = Mock(
        return_value=subprocess.CompletedProcess(
            args=[crontab_utils.CRON_COMMAND, "-r"],
            returncode=0,
            stdout=b"",
            stderr=b"",
        )
    )
    monkeypatch.setattr(crontab_utils.subprocess, "run", run)
    monkeypatch.setattr(
        crontab_utils, "install_crontab_snapshot", install_exact_crontab_snapshot
    )

    crontab_utils.install_crontab_snapshot(crontab_utils.CrontabSnapshot(b"", False))

    run.assert_called_once_with(
        [crontab_utils.CRON_COMMAND, "-r"],
        capture_output=True,
        check=False,
        timeout=15,
    )


def test_all_app_crud_mutations_record_exact_before_and_after_snapshots(monkeypatch):
    state = {
        "snapshot": crontab_utils.CrontabSnapshot(
            b"MAILTO=admin@example.test\r\n# preserved comment\r\n\r\n", True
        )
    }
    monkeypatch.setattr(
        crontab_utils, "get_crontab_snapshot", lambda: state["snapshot"]
    )

    def mutate(marker):
        def action(*_args, **_kwargs):
            current = state["snapshot"]
            state["snapshot"] = crontab_utils.CrontabSnapshot(
                current.content + marker, current.exists
            )

        return action

    monkeypatch.setattr(crontab_utils, "add_cron_job", mutate(b"# add\r\n"))
    monkeypatch.setattr(crontab_utils, "update_cron_job", mutate(b"# update\r\n"))
    monkeypatch.setattr(crontab_utils, "remove_cron_job", mutate(b"# delete\r\n"))
    monkeypatch.setattr(crontab_utils, "duplicate_cron_job", mutate(b"# duplicate\r\n"))
    monkeypatch.setattr(crontab_utils, "import_cron_jobs", mutate(b"# import\r\n"))

    requests = [
        client.post(
            "/api/cron-jobs",
            json={"schedule": "0 * * * *", "command": "echo add", "enabled": True},
        ),
        client.put(
            "/api/cron-jobs",
            json={
                "index": 0,
                "schedule": "0 * * * *",
                "command": "echo update",
                "enabled": True,
            },
        ),
        client.delete("/api/cron-jobs/0"),
        client.post("/api/cron-jobs/0/duplicate"),
        client.post(
            "/api/cron-jobs/import",
            json={
                "jobs": [
                    {"schedule": "0 * * * *", "command": "echo import", "enabled": True}
                ]
            },
        ),
    ]

    assert [response.status_code for response in requests] == [200] * 5
    entries = storage.list_crontab_changes(20, 0)
    assert {entry["operation"] for entry in entries} == {
        "add",
        "update",
        "delete",
        "duplicate",
        "import",
    }
    assert all(entry["outcome"] == "succeeded" for entry in entries)
    history_response = client.get("/api/crontab-history?limit=20")
    assert history_response.status_code == 200
    assert len(history_response.json()["items"]) == 5
    first = client.get(f"/api/crontab-history/{entries[-1]['id']}").json()
    assert (
        first["before_text"]
        == "MAILTO=admin@example.test\r\n# preserved comment\r\n\r\n"
    )
    assert first["after_text"] == first["before_text"] + "# add\r\n"
    assert "# preserved comment" in first["diff"]


def test_app_mutations_serialize_read_write_and_verification(monkeypatch):
    state = {"content": b"# initial\\r\\n"}
    reads = []
    read_lock = threading.Lock()
    first_action_entered = threading.Event()
    allow_first_write = threading.Event()
    first_after_snapshot_entered = threading.Event()
    allow_first_verification = threading.Event()
    second_action_entered = threading.Event()
    failures = []

    def get_snapshot():
        thread_name = threading.current_thread().name
        with read_lock:
            reads.append((thread_name, state["content"]))
            is_first_after = (
                thread_name == "cron-first"
                and sum(1 for name, _ in reads if name == "cron-first") == 2
            )
        if is_first_after:
            first_after_snapshot_entered.set()
            assert allow_first_verification.wait(timeout=3)
        return crontab_utils.CrontabSnapshot(state["content"], True)

    def first_action():
        first_action_entered.set()
        assert allow_first_write.wait(timeout=3)
        state["content"] += b"# first write\\r\\n"

    def second_action():
        second_action_entered.set()
        state["content"] += b"# second write\\r\\n"

    def run(operation, action):
        try:
            audited_change(operation, operation, action)
        except Exception as exc:  # surfaced in the main test thread below
            failures.append(exc)

    monkeypatch.setattr(crontab_utils, "get_crontab_snapshot", get_snapshot)
    first = threading.Thread(
        target=run, args=("first", first_action), name="cron-first"
    )
    second = threading.Thread(
        target=run, args=("second", second_action), name="cron-second"
    )
    first.start()
    assert first_action_entered.wait(timeout=3)
    second.start()
    time.sleep(0.1)
    assert not second_action_entered.is_set()
    assert [name for name, _ in reads] == ["cron-first"]

    allow_first_write.set()
    assert first_after_snapshot_entered.wait(timeout=3)
    time.sleep(0.1)
    assert not second_action_entered.is_set()
    assert [name for name, _ in reads] == ["cron-first", "cron-first"]

    allow_first_verification.set()
    first.join(timeout=3)
    second.join(timeout=3)
    assert not first.is_alive() and not second.is_alive()
    assert failures == []

    records = storage.list_crontab_changes(2, 0)
    second_change = storage.get_crontab_change(records[0]["id"])
    first_change = storage.get_crontab_change(records[1]["id"])
    assert first_change["before_snapshot"] == b"# initial\\r\\n"
    assert first_change["after_snapshot"] == b"# initial\\r\\n# first write\\r\\n"
    assert second_change["before_snapshot"] == first_change["after_snapshot"]
    assert second_change["after_snapshot"] == state["content"]


def test_interrupted_pending_change_records_recovery_observation_without_guessing(
    monkeypatch,
):
    change_id = storage.begin_crontab_change(
        "update", "Simulate interrupted update", b"# before\n", True
    )
    current = crontab_utils.CrontabSnapshot(b"# current after restart\r\n", True)
    unchanged_change_id = storage.begin_crontab_change(
        "delete", "Interrupted before write", current.content, True
    )
    monkeypatch.setattr(crontab_utils, "get_crontab_snapshot", lambda: current)

    assert recover_pending_changes() == 2
    for recovered_id in (change_id, unchanged_change_id):
        entry = storage.get_crontab_change(recovered_id)
        assert entry["outcome"] == "unknown"
        assert entry["after_snapshot"] == current.content
        assert entry["after_exists"] == 1
        assert entry["after_snapshot_source"] == "recovery_observation"
        assert "exact current crontab observed during recovery" in entry["error"]


def test_recovery_keeps_outcome_unknown_when_live_snapshot_is_unavailable(
    monkeypatch,
):
    change_id = storage.begin_crontab_change(
        "add", "Interrupted change", b"# before\n", True
    )
    monkeypatch.setattr(
        crontab_utils,
        "get_crontab_snapshot",
        Mock(side_effect=RuntimeError("crontab is unavailable")),
    )

    assert recover_pending_changes() == 1
    entry = storage.get_crontab_change(change_id)
    assert entry["outcome"] == "unknown"
    assert entry["after_snapshot"] is None
    assert entry["after_snapshot_source"] == "unavailable"
    assert "crontab is unavailable" in entry["error"]


def test_failed_app_change_is_persisted_with_exact_unchanged_snapshots(monkeypatch):
    snapshot = crontab_utils.CrontabSnapshot(b"# comments stay\n\n", True)
    monkeypatch.setattr(crontab_utils, "get_crontab_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        crontab_utils,
        "add_cron_job",
        Mock(side_effect=ValueError("Invalid cron schedule")),
    )

    response = client.post(
        "/api/cron-jobs",
        json={"schedule": "bad", "command": "echo no", "enabled": True},
    )

    assert response.status_code == 400
    entry = storage.list_crontab_changes(1, 0)[0]
    detail = client.get(f"/api/crontab-history/{entry['id']}").json()
    assert entry["outcome"] == "failed"
    assert detail["before_text"] == "# comments stay\n\n"
    assert detail["after_text"] == detail["before_text"]
    assert detail["error"] == "Invalid cron schedule"


def make_successful_change(monkeypatch, before, after):
    state = {"snapshot": crontab_utils.CrontabSnapshot(before, True)}
    monkeypatch.setattr(
        crontab_utils, "get_crontab_snapshot", lambda: state["snapshot"]
    )

    def apply_requested_change(_job):
        state["snapshot"] = crontab_utils.CrontabSnapshot(after, True)

    monkeypatch.setattr(crontab_utils, "add_cron_job", apply_requested_change)
    response = client.post(
        "/api/cron-jobs",
        json={"schedule": "0 * * * *", "command": "echo changed", "enabled": True},
    )
    assert response.status_code == 200
    change_id = response.json()["change_id"]
    return state, change_id


def test_preview_and_rollback_restore_exact_snapshot_and_record_rollback(monkeypatch):
    before = b"SHELL=/bin/bash\r\n# comment\r\n\r\n0 * * * * echo old\r\n"
    after = b"SHELL=/bin/bash\r\n# comment\r\n\r\n0 * * * * echo new\r\n"
    state, change_id = make_successful_change(monkeypatch, before, after)

    preview = client.get(f"/api/crontab-history/{change_id}/rollback-preview").json()
    assert preview["can_rollback"] is True
    assert preview["stale"] is False
    assert "-0 * * * * echo new" in preview["diff"]
    assert "+SHELL=/bin/bash" not in preview["diff"]

    def install_snapshot(snapshot):
        state["snapshot"] = snapshot

    monkeypatch.setattr(crontab_utils, "install_crontab_snapshot", install_snapshot)
    response = client.post(
        f"/api/crontab-history/{change_id}/rollback",
        json={"expected_current_sha256": preview["expected_current_sha256"]},
    )

    assert response.status_code == 200
    assert state["snapshot"].content == before
    rollback = storage.get_crontab_change(response.json()["change_id"])
    assert rollback["operation"] == "rollback"
    assert rollback["related_change_id"] == change_id
    assert rollback["outcome"] == "succeeded"
    assert rollback["after_snapshot"] == before


def test_rollback_distinguishes_empty_crontab_from_missing_crontab(monkeypatch):
    change_id = storage.begin_crontab_change(
        "delete", "Remove final cron line", b"", False
    )
    storage.finish_crontab_change(
        change_id,
        after_snapshot=b"",
        after_exists=True,
        outcome="succeeded",
    )
    state = {"snapshot": crontab_utils.CrontabSnapshot(b"", True)}
    monkeypatch.setattr(
        crontab_utils, "get_crontab_snapshot", lambda: state["snapshot"]
    )
    installed = []

    def install(snapshot):
        installed.append(snapshot)
        state["snapshot"] = snapshot

    monkeypatch.setattr(crontab_utils, "install_crontab_snapshot", install)
    preview = client.get(f"/api/crontab-history/{change_id}/rollback-preview").json()

    assert preview["can_rollback"] is True
    assert preview["target_exists"] is False
    assert preview["diff"] == ""
    response = client.post(
        f"/api/crontab-history/{change_id}/rollback",
        json={"expected_current_sha256": preview["expected_current_sha256"]},
    )

    assert response.status_code == 200
    assert installed == [crontab_utils.CrontabSnapshot(b"", False)]
    assert state["snapshot"].content == b""
    assert state["snapshot"].exists is False


def test_rollback_refuses_stale_state_after_preview(monkeypatch):
    before = b"# original\n0 * * * * echo old\n"
    after = b"# original\n0 * * * * echo new\n"
    state, change_id = make_successful_change(monkeypatch, before, after)
    preview = client.get(f"/api/crontab-history/{change_id}/rollback-preview").json()
    assert preview["can_rollback"] is True

    state["snapshot"] = crontab_utils.CrontabSnapshot(
        b"# externally changed since preview\n", True
    )
    installer = Mock()
    monkeypatch.setattr(crontab_utils, "install_crontab_snapshot", installer)
    response = client.post(
        f"/api/crontab-history/{change_id}/rollback",
        json={"expected_current_sha256": preview["expected_current_sha256"]},
    )

    assert response.status_code == 409
    assert "changed since the rollback preview" in response.json()["detail"]
    installer.assert_not_called()
    assert state["snapshot"].content == b"# externally changed since preview\n"
