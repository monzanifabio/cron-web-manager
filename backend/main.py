from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cron_routes import router
import socket


app = FastAPI(
    title="Cron Web Manager",
    description="Manage system cron jobs through a web interface",
    version="0.1.0"
)

# Enable CORS (adjust allowed origins in production)
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