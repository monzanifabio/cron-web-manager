import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import crontab  # noqa: E402

import crontab_utils  # noqa: E402
import storage  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_database_and_forbid_host_crontab(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test-cron-manager.sqlite3"))
    monkeypatch.delenv("CRON_LOG_PATH", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    storage.initialize_database()

    def forbidden_crontab(*_args, **_kwargs):
        raise AssertionError("Tests must not access the real host crontab")

    monkeypatch.setattr(crontab, "CronTab", forbidden_crontab)
    monkeypatch.setattr(crontab_utils, "CronTab", forbidden_crontab)
    monkeypatch.setattr(
        crontab_utils,
        "get_crontab_snapshot",
        lambda: crontab_utils.CrontabSnapshot(b"", False),
    )
    monkeypatch.setattr(
        crontab_utils,
        "install_crontab_snapshot",
        lambda _snapshot: (_ for _ in ()).throw(
            AssertionError("Tests must not install a real host crontab")
        ),
    )
