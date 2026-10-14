import asyncio
import os
import socket
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import cron_log_monitor
import storage
from auth import verify_api_key
from cron_routes import router
from crontab_audit import recover_pending_changes
from crontab_history_routes import router as crontab_history_router
from execution_routes import router as execution_router
from settings_routes import router as settings_router


@asynccontextmanager
async def lifespan(_app):
    storage.initialize_database()
    recover_pending_changes()
    monitor_task = asyncio.create_task(cron_log_monitor.monitor_loop())
    try:
        yield
    finally:
        monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task


app = FastAPI(
    title="Cron Web Manager",
    description="Manage system cron jobs through a web interface",
    version="0.1.0",
    lifespan=lifespan,
)

# 1. REMOVED: The CORSMiddleware is no longer needed.

# 2. ADDED: Include the API router before the static file serving.
# This ensures that API calls like /api/cron-jobs are handled correctly.
app.include_router(router, dependencies=[Depends(verify_api_key)])
app.include_router(execution_router, dependencies=[Depends(verify_api_key)])
app.include_router(crontab_history_router, dependencies=[Depends(verify_api_key)])
app.include_router(settings_router, dependencies=[Depends(verify_api_key)])


# Health check and hostname routes remain the same
@app.get("/api/health")
def health_check():
    health = {"status": "ok"}
    problems = []
    try:
        # Actually test crontab access
        from crontab import CronTab

        cron = CronTab(user=True)
        list(cron)  # Verify we can read it
    except Exception as e:
        problems.append(f"Crontab access failed: {str(e)}")
    if problems:
        health["status"] = "error"
        health["problems"] = problems
    health["cron_log_monitoring"] = cron_log_monitor.monitoring_status()
    return health


@app.get("/api/hostname")
def get_hostname():
    try:
        hostname = socket.gethostname()
        return {"hostname": hostname}
    except Exception as e:
        return {"error": str(e)}


# 3. ADDED: Logic to serve the static frontend files
# This should come AFTER all your API routes.

# Define the directory where your built Vite app is located
DIST_DIR = "dist"

# Mount the 'assets' folder from the 'dist' directory
# Vite typically puts JS and CSS files in an 'assets' subfolder.
assets_path = os.path.join(DIST_DIR, "assets")
if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")


# A catch-all route to serve 'index.html' for any other path.
# This is essential for client-side routing in SPAs.
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    from fastapi import HTTPException

    # Don't catch API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    index_path = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend not found")
