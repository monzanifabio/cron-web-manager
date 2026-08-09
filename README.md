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

---

## Production build

```bash
cd frontend
npm run build          # outputs to backend/dist/
uvicorn main:app --host 0.0.0.0 --port 8000
```

The backend serves the compiled frontend from `backend/dist/` at the root path.

---

## Docker

```bash
docker-compose up --build
```

> **Note:** crontab access requires the container to share the host's cron spool. On Linux, uncomment the `volumes` section in `docker-compose.yml`. This setup is primarily intended for Linux hosts — on macOS, cron jobs are managed by launchd.

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
