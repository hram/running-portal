from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from portal.db import connect_db, get_activity, get_settings, init_db, normalize_db_path
from portal.infrastructure import config
from portal.routers import activities, ai, auth, settings, sync


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(_: FastAPI):
    from portal.scheduler import start as start_scheduler
    from portal.scheduler import stop as stop_scheduler

    db_path = normalize_db_path(config.DB_PATH)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    await init_db(db_path)
    logger.info("Database initialized at %s", db_path)
    start_scheduler()
    logger.info("Scheduler started")
    try:
        yield
    finally:
        stop_scheduler()
        logger.info("Scheduler stopped")


app = FastAPI(lifespan=lifespan)
app.include_router(activities.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/activity/{activity_id}", response_class=HTMLResponse)
async def activity_detail_page(activity_id: str, request: Request) -> HTMLResponse:
    conn = await connect_db(normalize_db_path(config.DB_PATH))
    try:
        activity = await get_activity(conn, activity_id)
        settings_payload = await get_settings(conn)
    finally:
        await conn.close()

    if activity is None:
        return templates.TemplateResponse(
            request,
            "detail.html",
            {"activity": None, "activity_id": activity_id},
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "detail.html",
        {"activity": dict(activity), "activity_id": activity_id, "settings": settings_payload},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    conn = await connect_db(normalize_db_path(config.DB_PATH))
    try:
        settings_payload = await get_settings(conn)
    finally:
        await conn.close()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings_payload},
    )
