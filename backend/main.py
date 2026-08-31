from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.database import init_db
from backend.downloader import manager
from backend.routes import router as api_router
from backend.config import BASE_DIR

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and background downloader worker loops
    init_db()
    manager.start()
    yield
    # Shutdown: clean up background workers
    manager._running = False

app = FastAPI(
    title="Telegram Video Downloader",
    description="Modern, lightweight, browser-based Telegram Video Downloader without login requirement.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for any frontend client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)

# Mount static folder
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
(static_dir / "css").mkdir(parents=True, exist_ok=True)
(static_dir / "js").mkdir(parents=True, exist_ok=True)
(static_dir / "assets").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def serve_index():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Telegram Video Downloader API running. Static UI not found."}
