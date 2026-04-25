from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from portal.db import (
    connect_db,
    get_activities,
    get_activities_for_ef,
    get_activity,
    get_activity_count,
    get_detail,
)
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
        serialized: list[dict[str, Any]] = []
        for activity in activities:
            detail = await get_detail(conn, activity["activity_id"])
            serialized.append(
                {
                    **_serialize_activity_row(activity),
                    "has_details": detail is not None,
                }
            )
        total = await get_activity_count(conn)
        return {
            "activities": serialized,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        await conn.close()


@router.get("/activities/progress")
async def get_progress() -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        activities = await get_activities_for_ef(conn)
    finally:
        await conn.close()

    if not activities:
        return {"weeks": [], "summary": {}}

    weekly: dict[str, list[float]] = defaultdict(list)
    weekly_labels: dict[str, str] = {}

    for activity in activities:
        date_str = activity["date"]
        try:
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        except Exception:
            continue

        iso_year, iso_week, _ = dt.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        monday = dt.date().fromisocalendar(iso_year, iso_week, 1)
        weekly_labels.setdefault(week_key, monday.strftime("%d.%m"))

        pace = activity.get("avg_pace")
        hrm = activity.get("avg_hrm")
        if pace and hrm and pace > 0 and hrm > 0:
            speed_mpm = 1000 / pace * 60
            ef = round(speed_mpm / hrm, 3)
            weekly[week_key].append(ef)

    weeks_data: list[dict[str, object]] = []
    for week_key in sorted(weekly.keys()):
        values = weekly[week_key]
        if values:
            weeks_data.append(
                {
                    "week": week_key,
                    "label": weekly_labels[week_key],
                    "ef": round(sum(values) / len(values), 3),
                    "runs": len(values),
                }
            )

    if not weeks_data:
        return {"weeks": [], "summary": {}}

    ef_values = [float(week["ef"]) for week in weeks_data]
    first_ef = ef_values[0]
    last_ef = ef_values[-1]
    max_ef = max(ef_values)
    peak_week = str(weeks_data[ef_values.index(max_ef)]["label"])

    trend = None
    if len(ef_values) >= 6:
        recent = sum(ef_values[-3:]) / 3
        prev = sum(ef_values[-6:-3]) / 3
        if prev > 0:
            trend = round((recent - prev) / prev * 100, 1)

    return {
        "weeks": weeks_data,
        "summary": {
            "first_ef": first_ef,
            "last_ef": last_ef,
            "max_ef": max_ef,
            "peak_week": peak_week,
            "trend": trend,
            "total_weeks": len(weeks_data),
        },
    }


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


@router.post("/activities/details/load-all")
async def load_all_activity_details() -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        activities = await get_activities(conn, limit=10000, offset=0)
        pending_ids: list[str] = []
        for activity in activities:
            detail = await get_detail(conn, activity["activity_id"])
            if detail is None:
                pending_ids.append(str(activity["activity_id"]))
    finally:
        await conn.close()

    loaded = 0
    failed: list[str] = []
    for activity_id in pending_ids:
        details = await fetch_detail(activity_id)
        if details is None:
            failed.append(activity_id)
        else:
            loaded += 1

    return {
        "total": len(pending_ids),
        "loaded": loaded,
        "failed": len(failed),
        "failed_activity_ids": failed,
    }

