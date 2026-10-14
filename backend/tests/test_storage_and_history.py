import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import cron_log_monitor  # noqa: E402
import storage  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def configure_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "cron-manager.sqlite3"))
    monkeypatch.delenv("CRON_LOG_PATH", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    storage.initialize_database()


def test_sqlite_persists_application_settings_and_supports_delete(
    monkeypatch, tmp_path
):
    configure_database(monkeypatch, tmp_path)

    saved = client.put("/api/settings/timezone", json={"value": "Europe/London"})
    storage.initialize_database()  # Reinitialization must retain saved settings.
    loaded = client.get("/api/settings")
    deleted = client.delete("/api/settings/timezone")

    assert saved.status_code == 200
    assert saved.json() == {"key": "timezone", "value": "Europe/London"}
    assert loaded.status_code == 200
    assert loaded.json()["settings"]["timezone"]["value"] == "Europe/London"
    assert loaded.json()["settings"]["timezone"]["updated_at"]
    assert deleted.status_code == 200
    assert client.delete("/api/settings/timezone").status_code == 404


def test_settings_reject_invalid_keys_and_non_json_values(monkeypatch, tmp_path):
    configure_database(monkeypatch, tmp_path)

    assert client.put("/api/settings/bad%20key", json={"value": 1}).status_code == 400
    non_finite = client.put(
        "/api/settings/nan",
        content='{"value":NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert non_finite.status_code == 422


def test_cron_log_ingestion_records_launch_without_claiming_success(
    monkeypatch, tmp_path
):
    configure_database(monkeypatch, tmp_path)
    log_path = tmp_path / "syslog"
    now = datetime.now().astimezone()
    line = (
        f"{now.strftime('%b')} {now.day:2} {now.strftime('%H:%M:%S')} host "
        "CRON[2468]: (deploy) CMD (/opt/jobs/nightly.sh --quiet)\n"
    )
    log_path.write_text(line, encoding="utf-8")
    monkeypatch.setenv("CRON_LOG_PATH", str(log_path))

    first = cron_log_monitor.ingest_configured_cron_log()
    second = cron_log_monitor.ingest_configured_cron_log()
    response = client.get("/api/execution-history")
    event = response.json()["items"][0]

    assert first["available"] is True
    assert first["new_events"] == 1
    assert second["new_events"] == 0
    assert response.status_code == 200
    assert event["event_type"] == "launch_observed"
    assert event["outcome"] == "unknown"
    assert event["username"] == "deploy"
    assert event["process_id"] == 2468
    assert event["command"] == "/opt/jobs/nightly.sh --quiet"


def test_systemd_journal_directory_records_cmd_launches_only(monkeypatch, tmp_path):
    configure_database(monkeypatch, tmp_path)
    journal_path = tmp_path / "journal"
    journal_path.mkdir()
    (journal_path / "system.journal").write_bytes(b"journal fixture")
    monkeypatch.setenv("CRON_LOG_PATH", str(journal_path))
    event = {
        "__CURSOR": "cursor-1",
        "__REALTIME_TIMESTAMP": str(
            int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        ),
        "SYSLOG_IDENTIFIER": "CRON",
        "SYSLOG_PID": "987",
        "MESSAGE": "(pi) CMD (/home/pi/job.sh)",
    }
    output = json.dumps(event) + "\n-- cursor: cursor-1\n"
    completed = subprocess.CompletedProcess(
        args=["journalctl"], returncode=0, stdout=output, stderr=""
    )

    with patch("cron_log_monitor.subprocess.run", return_value=completed) as run:
        result = cron_log_monitor.ingest_configured_cron_log()

    stored = storage.list_execution_history(10, 0)
    assert result["available"] is True
    assert result["new_events"] == 1
    assert stored[0]["command"] == "/home/pi/job.sh"
    assert stored[0]["outcome"] == "unknown"
    assert "--directory=" + str(journal_path) in run.call_args.args[0]


def test_partial_log_line_is_ingested_after_it_is_completed(monkeypatch, tmp_path):
    configure_database(monkeypatch, tmp_path)
    log_path = tmp_path / "cron.log"
    now = datetime.now().astimezone()
    full_line = (
        f"{now.strftime('%b')} {now.day:2} {now.strftime('%H:%M:%S')} host "
        "CROND[12]: (root) CMD (echo partial)\n"
    )
    encoded_line = full_line.encode()
    split_at = len(encoded_line) - 5
    log_path.write_bytes(encoded_line[:split_at])
    monkeypatch.setenv("CRON_LOG_PATH", str(log_path))

    partial_result = cron_log_monitor.ingest_configured_cron_log()
    with log_path.open("ab") as log_file:
        log_file.write(encoded_line[split_at:])
    completed_result = cron_log_monitor.ingest_configured_cron_log()

    assert partial_result["new_events"] == 0
    assert completed_result["new_events"] == 1
    assert storage.list_execution_history(10, 0)[0]["command"] == "echo partial"


def test_add_cron_job_remains_unwrapped_when_host_log_is_unavailable(
    monkeypatch, tmp_path
):
    configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv("CRON_LOG_PATH", str(tmp_path / "missing-host-log"))
    cron = MagicMock()
    cron_job = MagicMock()
    cron_job.is_valid.return_value = True
    cron.new.return_value = cron_job

    with patch("crontab_utils.CronTab", return_value=cron):
        response = client.post(
            "/api/cron-jobs",
            json={
                "schedule": "*/5 * * * *",
                "command": "echo cron-behaviour-unchanged",
                "enabled": True,
                "comment": "test",
            },
        )

    assert response.status_code == 200
    cron.new.assert_called_once_with(
        command="echo cron-behaviour-unchanged",
        comment="test",
    )
    cron.write.assert_called_once()


def test_unavailable_monitor_does_not_break_crud(monkeypatch, tmp_path):
    configure_database(monkeypatch, tmp_path)
    monkeypatch.setenv("CRON_LOG_PATH", str(tmp_path / "missing-host-log"))

    history = client.get("/api/execution-history")
    with patch("crontab_utils.CronTab") as mock_cron:
        mock_cron.return_value.__iter__ = MagicMock(return_value=iter([]))
        jobs = client.get("/api/cron-jobs")

    assert history.status_code == 200
    assert history.json()["monitoring"]["available"] is False
    assert jobs.status_code == 200
    assert jobs.json() == []
