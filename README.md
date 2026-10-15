# cron-web-manager

A web interface for managing system cron jobs, with a FastAPI backend and a vanilla JS + Bootstrap frontend built with Vite.

---

## Development setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
cp .env.example .env   # edit VITE_API_BASE_URL if needed
npm install
npm run dev            # serves on http://localhost:8080, proxies /api → :8000
```

The Vite dev server proxies all `/api` requests to `http://localhost:8000`, so no CORS configuration or `.env` changes are needed for local development.

To preview the production UI locally without running the backend, start the frontend in mock mode:

```bash
cd frontend
npm run dev:mock
```

This uses seeded fake cron jobs in the browser and keeps add/edit/delete/import/duplicate changes in local storage while mock mode is active.

---

## Production build

```bash
npm run start:prod
```

This command builds the frontend into `backend/dist/` and then starts the FastAPI app from `backend/`. The backend serves the compiled frontend from `backend/dist/` at the root path.

You can override the bind settings if needed:

```bash
HOST=127.0.0.1 PORT=9000 npm run start:prod
```

---

## Persistence and execution history

The current user's crontab remains the sole source of truth for scheduled job definitions. SQLite stores application settings and observed execution events; it does not mirror or replace the crontab.

- `DATABASE_PATH` selects the SQLite file. By default it is `backend/data/cron-web-manager.sqlite3`; the Docker Compose setup stores it in the persistent `cron_manager_data` volume.
- `CRON_LOG_PATH` is optional and unset by default. For Docker, use the `docker-compose.cron-logs.yml` overlay: set `CRON_LOG_HOST_PATH` to the host's plaintext cron log or systemd journal directory, and `CRON_LOG_GID` to the host group allowed to read it. The overlay mounts that source read-only at `/host/cron-logs`; the app reads that container path. On systemd hosts, the monitor uses `journalctl` against a mounted journal directory; on syslog hosts, it parses standard CRON/CROND `CMD` lines. Paths and group permissions vary by host.
- `CRON_LOG_POLL_SECONDS` controls polling and defaults to 10 seconds.

For example, on a systemd host where `systemd-journal` is the readable group, start with `CRON_LOG_HOST_PATH=/run/log/journal CRON_LOG_GID=$(getent group systemd-journal | cut -d: -f3) docker compose -f docker-compose.yml -f docker-compose.cron-logs.yml up --build`. Verify the configured host path exists and the chosen group can read it before enabling the overlay.

The execution-history view and `GET /api/execution-history?limit=100&offset=0` endpoint store cron daemon `CMD` launch observations incrementally in SQLite and survive application restarts. A launch event is **not** evidence that a command completed or succeeded: every recorded outcome is explicitly `unknown`. If `CRON_LOG_PATH` is unset, missing, or unreadable, monitoring reports unavailable/disabled and the existing crontab CRUD endpoints continue to work normally. Existing cron commands are never rewritten for monitoring. The protected settings API is `GET /api/settings`, `PUT /api/settings/{key}` with `{"value": ...}`, and `DELETE /api/settings/{key}`.

Crontab Change History records every app-driven add, update, delete, duplicate, import, and rollback in SQLite, including success/failure/unknown outcomes and exact before/after bytes obtained directly from `crontab -l` (without rebuilding snapshots from parsed jobs). App mutations hold a thread and cross-worker advisory lock across the before read, SQLite pending record, write, after read, and outcome commit. A process restart reconciles pending records by capturing the exact current crontab and marking the outcome `unknown`; that recovery observation is not presented as proof of the interrupted operation's result. The UI shows unified diffs. A rollback must be previewed; applying it checks a fresh snapshot against both the preview hash and the selected change's recorded state hash, refuses stale state, restores the original bytes directly through `crontab(1)`, and verifies both exact bytes and whether the crontab exists. The lock coordinates app workers sharing the same database path; direct external crontab writers do not participate in that lock. The protected API is `GET /api/crontab-history`, `GET /api/crontab-history/{id}`, `GET /api/crontab-history/{id}/rollback-preview`, and `POST /api/crontab-history/{id}/rollback` with `{"expected_current_sha256": "..."}`. Tests replace all crontab access with deterministic mocks and never touch the host crontab.

## Docker

```bash
docker-compose up --build
```

> **Note:** crontab access requires the container to share the host's cron spool. On Linux, uncomment and adjust the crontab `volumes` section in `docker-compose.yml`. Host cron logs are a separate opt-in mount; the app does not assume it can access them. This setup is primarily intended for Linux hosts — on macOS, cron jobs are managed by launchd.

### Authentication

Set the `API_KEY` environment variable to protect the API with a header-based key:

```bash
API_KEY=mysecretkey docker-compose up --build
```

All `/api/cron-jobs` requests must then include the header `X-API-Key: mysecretkey`. If `API_KEY` is not set, authentication is skipped (dev mode).

---

## Linting & formatting (frontend)

```bash
npm run lint      # ESLint
npm run format    # Prettier
```

## Linting (backend)

```bash
pip install -r requirements-dev.txt
ruff check .
```

## Tests (backend)

```bash
pip install -r requirements-dev.txt
pytest tests/
```
