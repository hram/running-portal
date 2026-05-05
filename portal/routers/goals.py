from __future__ import annotations

import calendar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from portal.db import (
    connect_db,
    get_activities,
    get_monthly_goal,
    get_monthly_progress,
    save_monthly_goal,
)
from portal.infrastructure import config
from portal.routers.ai import generate_goal_suggestion


router = APIRouter()


class GoalRequest(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    km_goal: float = Field(gt=0, le=1000)
    runs_goal: int = Field(gt=0, le=31)
    ai_suggestion: str | None = None


def _resolve_db_path() -> str:
    return str(Path(config.DB_PATH).expanduser())


def _resolve_month(year: int | None, month: int | None) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    resolved_year = year or now.year
    resolved_month = month or now.month
    if not 1 <= resolved_month <= 12:
        raise HTTPException(status_code=422, detail="month must be in 1..12")
    if not 2000 <= resolved_year <= 2100:
        raise HTTPException(status_code=422, detail="year must be in 2000..2100")
    return resolved_year, resolved_month


def _month_timing(year: int, month: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    days_in_month = calendar.monthrange(year, month)[1]
    if now.year == year and now.month == month:
        current_day = now.day
    elif (year, month) < (now.year, now.month):
        current_day = days_in_month
    else:
        current_day = 0

    days_elapsed_pct = round(current_day / days_in_month * 100, 1)
    return {
        "days_in_month": days_in_month,
        "days_elapsed": current_day,
        "days_remaining": max(0, days_in_month - current_day),
        "days_elapsed_pct": days_elapsed_pct,
    }


def build_goal_payload(goal: dict[str, Any] | None, progress: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    timing = _month_timing(year, month)
    if goal is None:
        return {
            "goal": None,
            "progress": progress,
            **timing,
            "status": "no_goal",
        }

    km_goal = float(goal["km_goal"])
    runs_goal = int(goal["runs_goal"])
    km_pct = round(float(progress["total_km"]) / km_goal * 100, 1) if km_goal > 0 else 0.0
    runs_pct = round(int(progress["runs_count"]) / runs_goal * 100, 1) if runs_goal > 0 else 0.0
    expected = float(timing["days_elapsed_pct"])

    if km_pct >= expected - 5 and runs_pct >= expected - 10:
        status = "on_track"
    elif km_pct >= expected - 15 or runs_pct >= expected - 20:
        status = "slightly_behind"
    else:
        status = "behind"

    km_remaining = round(max(0.0, km_goal - float(progress["total_km"])), 1)
    runs_remaining = max(0, runs_goal - int(progress["runs_count"]))
    days_remaining = int(timing["days_remaining"])
    needed_km_per_day = round(km_remaining / days_remaining, 2) if days_remaining > 0 else km_remaining
    needed_km_per_run = round(km_remaining / runs_remaining, 1) if runs_remaining > 0 else 0.0

    return {
        "goal": goal,
        "progress": progress,
        **timing,
        "km_pct": km_pct,
        "runs_pct": runs_pct,
        "km_remaining": km_remaining,
        "runs_remaining": runs_remaining,
        "needed_km_per_day": needed_km_per_day,
        "needed_km_per_run": needed_km_per_run,
        "status": status,
    }


@router.get("/goals/monthly")
async def get_goal(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    year, month = _resolve_month(year, month)
    conn = await connect_db(_resolve_db_path())
    try:
        goal = await get_monthly_goal(conn, year, month)
        progress = await get_monthly_progress(conn, year, month)
    finally:
        await conn.close()
    return build_goal_payload(goal, progress, year, month)


@router.post("/goals/monthly")
async def set_goal(body: GoalRequest) -> dict[str, Any]:
    conn = await connect_db(_resolve_db_path())
    try:
        await save_monthly_goal(
            conn,
            year=body.year,
            month=body.month,
            km_goal=body.km_goal,
            runs_goal=body.runs_goal,
            ai_suggestion=body.ai_suggestion,
        )
        goal = await get_monthly_goal(conn, body.year, body.month)
        progress = await get_monthly_progress(conn, body.year, body.month)
    finally:
        await conn.close()
    return {"ok": True, **build_goal_payload(goal, progress, body.year, body.month)}


@router.get("/goals/monthly/suggest")
async def suggest_goal(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    year, month = _resolve_month(year, month)
    conn = await connect_db(_resolve_db_path())
    try:
        activities = await get_activities(conn, limit=60, offset=0)
    finally:
        await conn.close()
    return await generate_goal_suggestion(activities, year, month)
