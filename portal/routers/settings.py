from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from portal.db import connect_db, get_settings, save_setting
from portal.sync import _resolve_db_path


router = APIRouter()

EDITABLE_SETTING_KEYS = (
    "daily_prompt_template",
    "activity_prompt_template",
    "target_hr_zone_low",
    "target_hr_zone_high",
)


class SettingsUpdateRequest(BaseModel):
    daily_prompt_template: str
    activity_prompt_template: str
    target_hr_zone_low: int
    target_hr_zone_high: int


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
        settings = await get_settings(conn)
    finally:
        await conn.close()
    return {"ok": True, "settings": {key: settings[key] for key in EDITABLE_SETTING_KEYS}}
