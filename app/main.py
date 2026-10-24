import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.db import connect_db, close_db
from app.api import router

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    task = None
    if settings.role == "all":
        from app.worker import main as worker_main
        task = asyncio.create_task(worker_main())
    try:
        yield
    finally:
        if task:
            task.cancel()
        await close_db()


app = FastAPI(title="Telegram File Store Link Recovery", version="1.0.0", lifespan=lifespan)
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "web" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"ok": True, "service": "telegram-file-store-recovery"}
