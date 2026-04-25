from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from portal.db import connect_db, get_activities, get_activity, get_activity_count, get_detail
from portal.sync import _resolve_db_path, fetch_detail


router = APIRouter()


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _serialize_activity_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "raw_report": _decode_json(row.get("raw_report")),
    }


def _serialize_detail_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "samples": _decode_json(row.get("samples")) or [],
        "track_points": _decode_json(row.get("track_points")) or [],
        "raw_detail": _decode_json(row.get("raw_detail")),
    }


@router.get("/activities")
async def list_activities(limit: int = 20, offset: int = 0) -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        activities = await get_activities(conn, limit=limit, offset=offset)
        total = await get_activity_count(conn)
        return {
            "activities": [_serialize_activity_row(activity) for activity in activities],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        await conn.close()


@router.get("/activities/{activity_id}")
async def get_activity_by_id(activity_id: str) -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        activity = await get_activity(conn, activity_id)
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")
        detail = await get_detail(conn, activity_id)
        return {
            "activity": _serialize_activity_row(activity),
            "details": None if detail is None else _serialize_detail_row(detail),
        }
    finally:
        await conn.close()


@router.get("/activities/{activity_id}/detail")
async def get_activity_detail(activity_id: str) -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        activity = await get_activity(conn, activity_id)
    finally:
        await conn.close()

    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    details = await fetch_detail(activity_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Activity details not available")
    return {"activity_id": activity_id, "details": details}
