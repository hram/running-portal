from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from portal.db import (
    connect_db,
    create_health_state,
    delete_health_state,
    get_health_state,
    get_health_states,
    update_health_state,
)
from portal.infrastructure import config


router = APIRouter()


class HealthStateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    started_at: str = Field(min_length=1)
    ended_at: str | None = None

    @field_validator("description")
    @classmethod
    def description_must_have_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("description must not be blank")
        return text

    @field_validator("started_at", "ended_at")
    @classmethod
    def date_must_be_iso_like(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("date must be ISO formatted") from exc
        return value


def _resolve_db_path() -> str:
    return str(Path(config.DB_PATH).expanduser())


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _assert_date_order(body: HealthStateRequest) -> None:
    if body.ended_at is None:
        return
    started_at = _parse_datetime(body.started_at)
    ended_at = _parse_datetime(body.ended_at)
    if ended_at < started_at:
        raise HTTPException(status_code=422, detail="ended_at must be after started_at")


@router.get("/health-states")
async def list_health_states() -> dict[str, Any]:
    conn = await connect_db(_resolve_db_path())
    try:
        return {"states": await get_health_states(conn)}
    finally:
        await conn.close()


@router.post("/health-states", status_code=201)
async def add_health_state(body: HealthStateRequest) -> dict[str, Any]:
    _assert_date_order(body)
    conn = await connect_db(_resolve_db_path())
    try:
        state = await create_health_state(
            conn,
            description=body.description,
            started_at=body.started_at,
            ended_at=body.ended_at,
        )
    finally:
        await conn.close()
    return {"ok": True, "state": state}


@router.put("/health-states/{state_id}")
async def edit_health_state(state_id: int, body: HealthStateRequest) -> dict[str, Any]:
    _assert_date_order(body)
    conn = await connect_db(_resolve_db_path())
    try:
        existing = await get_health_state(conn, state_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Health state not found")
        state = await update_health_state(
            conn,
            state_id=state_id,
            description=body.description,
            started_at=body.started_at,
            ended_at=body.ended_at,
        )
    finally:
        await conn.close()
    return {"ok": True, "state": state}


@router.delete("/health-states/{state_id}")
async def remove_health_state(state_id: int) -> dict[str, Any]:
    conn = await connect_db(_resolve_db_path())
    try:
        deleted = await delete_health_state(conn, state_id)
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Health state not found")
    return {"ok": True}
