from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from portal.db import connect_db, get_settings, save_setting
from portal.infrastructure import config


router = APIRouter()

EDITABLE_SETTING_KEYS = (
    "daily_prompt_template",
    "activity_prompt_template",
    "target_hr_zone_low",
    "target_hr_zone_high",
    "dashboard_card_today",
    "dashboard_card_metrics",
    "dashboard_card_progress",
    "dashboard_card_goal",
    "dashboard_card_distance",
    "dashboard_card_runs",
)


class SettingsUpdateRequest(BaseModel):
    daily_prompt_template: str
    activity_prompt_template: str
    target_hr_zone_low: int
    target_hr_zone_high: int
    dashboard_card_today: bool = True
    dashboard_card_metrics: bool = True
    dashboard_card_progress: bool = True
    dashboard_card_goal: bool = True
    dashboard_card_distance: bool = True
    dashboard_card_runs: bool = True


def _resolve_db_path() -> str:
    return str(Path(config.DB_PATH).expanduser())


@router.get("/settings")
async def get_settings_payload() -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        settings = await get_settings(conn)
    finally:
        await conn.close()
    return {key: settings[key] for key in EDITABLE_SETTING_KEYS}


@router.post("/settings")
async def update_settings(body: SettingsUpdateRequest) -> dict[str, object]:
    conn = await connect_db(_resolve_db_path())
    try:
        await save_setting(conn, "daily_prompt_template", body.daily_prompt_template)
        await save_setting(conn, "activity_prompt_template", body.activity_prompt_template)
        await save_setting(conn, "target_hr_zone_low", str(body.target_hr_zone_low))
        await save_setting(conn, "target_hr_zone_high", str(body.target_hr_zone_high))
        await save_setting(conn, "dashboard_card_today", str(body.dashboard_card_today).lower())
        await save_setting(conn, "dashboard_card_metrics", str(body.dashboard_card_metrics).lower())
        await save_setting(conn, "dashboard_card_progress", str(body.dashboard_card_progress).lower())
        await save_setting(conn, "dashboard_card_goal", str(body.dashboard_card_goal).lower())
        await save_setting(conn, "dashboard_card_distance", str(body.dashboard_card_distance).lower())
        await save_setting(conn, "dashboard_card_runs", str(body.dashboard_card_runs).lower())
        settings = await get_settings(conn)
    finally:
        await conn.close()
    return {"ok": True, "settings": {key: settings[key] for key in EDITABLE_SETTING_KEYS}}
