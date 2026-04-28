from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter

from portal.db import connect_db, get_recent_sync_logs
from portal.infrastructure import config


router = APIRouter()


def _resolve_db_path() -> str:
    return str(Path(config.DB_PATH).expanduser())


async def sync_activities() -> dict[str, object]:
    from portal.sync import sync_activities as run_sync_activities

    return await run_sync_activities()


async def generate_daily_recommendation(sync_id: int | None = None) -> dict[str, str]:
    from portal.routers.ai import generate_daily_recommendation as generate

    return await generate(sync_id=sync_id)


@router.post("/sync")
async def run_sync() -> dict[str, object]:
    started_at = time.monotonic()
    result = await sync_activities()
    changed = int(result.get("added", 0)) > 0 or int(result.get("updated", 0)) > 0
    if result.get("error") is None and changed:
        result["recommendation"] = await generate_daily_recommendation(sync_id=result.get("sync_id"))
    else:
        result["recommendation"] = None
    result["duration_seconds"] = round(time.monotonic() - started_at, 3)
    return result


@router.get("/sync/status")
async def get_sync_status() -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        syncs = await get_recent_sync_logs(conn, limit=10)
        return {"syncs": syncs}
    finally:
        await conn.close()


@router.post("/ai/recommendation/refresh")
async def refresh_recommendation() -> dict[str, str]:
    return await generate_daily_recommendation()
