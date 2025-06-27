from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from cron_routes import router


app = FastAPI(
    title="Cron Web Manager",
    description="Manage system cron jobs through a web interface",
    version="0.1.0"
)

# Enable CORS (adjust allowed origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081"],  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(router)

# Health check route
@app.get("/api/health")
def health_check():
    return {"status": "ok"}
