import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def test_health_returns_200():
    with patch("crontab.CronTab") as mock_ct:
        mock_ct.return_value.__iter__ = MagicMock(return_value=iter([]))
        response = client.get("/api/health")
    assert response.status_code == 200


def test_hostname_returns_200():
    response = client.get("/api/hostname")
    assert response.status_code == 200
    data = response.json()
    assert "hostname" in data or "error" in data


def test_list_cron_jobs_returns_list():
    with patch("crontab_utils.CronTab") as mock_ct:
        mock_ct.return_value.__iter__ = MagicMock(return_value=iter([]))
        response = client.get("/api/cron-jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_add_cron_job_invalid_schedule():
    with patch("crontab_utils.CronTab") as mock_ct:
        mock_ct.return_value.new.side_effect = ValueError("Invalid schedule")
        response = client.post(
            "/api/cron-jobs",
            json={"schedule": "not-valid", "command": "echo hi", "enabled": True, "comment": ""},
        )
    assert response.status_code == 400
