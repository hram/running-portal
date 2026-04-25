from __future__ import annotations

import time

from fastapi import APIRouter

from portal.db import connect_db, get_recent_sync_logs
from portal.routers.ai import generate_daily_recommendation
from portal.sync import _resolve_db_path, sync_activities


router = APIRouter()


@router.post("/sync")
async def run_sync() -> dict[str, object]:
    started_at = time.monotonic()
    result = await sync_activities()
    if result.get("error") is None:
        await generate_daily_recommendation(sync_id=result.get("sync_id"))
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
