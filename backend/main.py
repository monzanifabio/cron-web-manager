from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from cron_routes import router
import socket
import os

app = FastAPI(
    title="Cron Web Manager",
    description="Manage system cron jobs through a web interface",
    version="0.1.0"
)

# 1. REMOVED: The CORSMiddleware is no longer needed.

# 2. ADDED: Include the API router before the static file serving.
# This ensures that API calls like /api/cron-jobs are handled correctly.
app.include_router(router)

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
    app.mount(
        "/assets",
        StaticFiles(directory=assets_path),
        name="assets"
    )

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