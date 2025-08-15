from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cron_routes import router
import socket
import os
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException


app = FastAPI(
    title="Cron Web Manager",
    description="Manage system cron jobs through a web interface",
    version="0.1.0"
)

# Enable CORS (adjust allowed origins in production)
# The origin http://localhost:8080 is for your frontend development server.
# When the frontend is served by FastAPI, you might not need CORS for same-origin requests,
# but it's good to keep for development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(router)

# Health check route
@app.get("/api/health")
def health_check():
    health = {"status": "ok"}
    problems = []

    # Example check: router is loaded (replace with real checks)
    try:
        if not router:
            problems.append("Router not loaded")
    except Exception as e:
        problems.append(f"Router check failed: {str(e)}")

    # Add more checks here (e.g., DB connection, file access, etc.)

    if problems:
        health["status"] = "error"
        health["problems"] = problems

    return health

# Hostname route
@app.get("/api/hostname")
def get_hostname():
    try:
        hostname = socket.gethostname()
        return {"hostname": hostname}
    except Exception as e:
        return {"error": str(e)}

# This class is a small wrapper around StaticFiles to make it suitable for
# serving a Single-Page Application (SPA). In the case of a 404 Not Found error,
# it falls back to serving the 'index.html' file.
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code == 404:
                # When a file is not found, serve index.html.
                # This is the key for single-page applications.
                return await super().get_response("index.html", scope)
            # Re-raise other exceptions
            raise ex

# The 'directory' path should be relative to where you run the uvicorn server,
# or an absolute path. We construct an absolute path for robustness.
# Path to the directory where this main.py file is located
backend_dir = os.path.dirname(os.path.abspath(__file__))
# Path to the frontend 'dist' folder, assuming it's at ../frontend/dist
frontend_dist_path = os.path.join(backend_dir, "..", "frontend", "dist")

# This must be the last mount, as it's a catch-all for any request
# that didn't match an API route.
app.mount("/", SPAStaticFiles(directory=frontend_dist_path, html=True), name="spa-static-files")
