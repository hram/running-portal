from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mi_fitness_sync.activity.client import MiFitnessActivitiesClient
from mi_fitness_sync.auth.client import MiFitnessAuthClient
from mi_fitness_sync.auth.store import DEFAULT_STATE_PATH, load_state
from mi_fitness_sync.fds.cache import DEFAULT_CACHE_DIR

from portal.db import (
    connect_db,
    get_activity,
    get_detail,
    log_sync_finish,
    log_sync_start,
    upsert_activity,
    upsert_detail,
)
from portal.infrastructure import config


logger = logging.getLogger(__name__)

DEFAULT_SYNC_LOOKBACK_DAYS = 90
DETAIL_CACHE_TTL_DAYS = 7
SYNC_PAGE_LIMIT = 1000


def _resolve_db_path() -> str:
    return str(Path(config.DB_PATH).expanduser())


def _resolve_state_path() -> str:
    return str(Path(config.MI_FITNESS_STATE_PATH or str(DEFAULT_STATE_PATH)).expanduser())


def _resolve_cache_dir() -> str:
    return str(Path(config.MI_FITNESS_CACHE_DIR or str(DEFAULT_CACHE_DIR)).expanduser())


def _resolve_country_code() -> str:
    return config.MI_FITNESS_COUNTRY_CODE or "RU"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_activity(activity: Any) -> dict[str, Any]:
    payload = activity.to_json_dict()
    raw_report = activity.raw_report if isinstance(activity.raw_report, dict) else {}

    def pick_int(*keys: str) -> int | None:
        for key in keys:
            value = raw_report.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str) and value.strip():
                try:
                    return int(float(value))
                except ValueError:
                    continue
        return None

    def pick_float(*keys: str) -> float | None:
        for key in keys:
            value = raw_report.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str) and value.strip():
                try:
                    return float(value)
                except ValueError:
                    continue
        return None

    start_time = activity.start_time or activity.raw_record.get("time") or 0
    date_value = datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()

    return {
        "activity_id": activity.activity_id,
        "date": date_value,
        "distance_km": payload.get("distance_km"),
        "duration_seconds": activity.duration_seconds,
        "avg_hrm": pick_int("avg_hrm", "avg_heart_rate", "heart_rate_avg"),
        "avg_pace": pick_int("avg_pace", "pace_avg"),
        "avg_cadence": pick_int("avg_cadence", "cadence_avg"),
        "avg_stride": pick_int("avg_stride", "avg_stride_length", "stride_avg"),
        "train_load": pick_int("train_load"),
        "recover_time": pick_int("recover_time", "recovery_time"),
        "vo2_max": pick_int("vo2_max"),
        "aerobic_train_effect": pick_float("aerobic_train_effect", "aerobic_te"),
        "anaerobic_train_effect": pick_float("anaerobic_train_effect", "anaerobic_te"),
        "hrm_warm_up_duration": pick_int("hrm_warm_up_duration"),
        "hrm_fat_burning_duration": pick_int("hrm_fat_burning_duration"),
        "hrm_aerobic_duration": pick_int("hrm_aerobic_duration"),
        "hrm_anaerobic_duration": pick_int("hrm_anaerobic_duration"),
        "hrm_extreme_duration": pick_int("hrm_extreme_duration"),
        "avg_vertical_stride_ratio": pick_float("avg_vertical_stride_ratio"),
        "avg_touchdown_duration": pick_int("avg_touchdown_duration"),
        "avg_vertical_amplitude": pick_float("avg_vertical_amplitude"),
        "raw_report": raw_report,
    }


def _deserialize_json_field(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _deserialize_detail_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "samples": _deserialize_json_field(row.get("samples")) or [],
        "track_points": _deserialize_json_field(row.get("track_points")) or [],
        "raw_detail": _deserialize_json_field(row.get("raw_detail")),
    }


def _parse_db_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def get_auth_client() -> MiFitnessAuthClient:
    return MiFitnessAuthClient()


def get_activity_client() -> MiFitnessActivitiesClient:
    auth_state = load_state(_resolve_state_path())
    if auth_state is None:
        raise RuntimeError("Mi Fitness auth state not found. Login is required before sync.")
    return MiFitnessActivitiesClient(
        auth_state,
        country_code=_resolve_country_code(),
        cache_dir=_resolve_cache_dir(),
    )


async def get_last_sync_date(conn) -> datetime | None:
    cursor = await conn.execute("SELECT date FROM activities ORDER BY date DESC LIMIT 1")
    row = await cursor.fetchone()
    if row is None:
        return None
    value = row["date"]
    if value is None:
        return None
    return _parse_db_datetime(str(value))


async def sync_activities(since: datetime | None = None) -> dict[str, Any]:
    conn = await connect_db(_resolve_db_path())
    sync_id = await log_sync_start(conn)
    try:
        effective_since = since or await get_last_sync_date(conn)
        if effective_since is None:
            effective_since = _utc_now() - timedelta(days=DEFAULT_SYNC_LOOKBACK_DAYS)
        if effective_since.tzinfo is None:
            effective_since = effective_since.replace(tzinfo=timezone.utc)

        client = get_activity_client()
        activities = await asyncio.to_thread(
            client.list_activities,
            start_time=int(effective_since.timestamp()),
            end_time=None,
            limit=SYNC_PAGE_LIMIT,
            category=None,
        )

        filtered = [
            activity
            for activity in activities
            if activity.category == "running"
            and activity.distance_meters is not None
            and (activity.distance_meters / 1000) > 0.3
        ]

        added = 0
        updated = 0
        for activity in filtered:
            existing = await get_activity(conn, activity.activity_id)
            if existing is None:
                added += 1
            else:
                updated += 1
            await upsert_activity(conn, _serialize_activity(activity))

        await log_sync_finish(conn, sync_id, added=added, updated=updated, error=None)
        return {"added": added, "updated": updated, "total": len(filtered), "error": None, "sync_id": sync_id}
    except Exception as exc:
        logger.exception("Sync failed")
        await log_sync_finish(conn, sync_id, added=0, updated=0, error=str(exc))
        return {"added": 0, "updated": 0, "total": 0, "error": str(exc), "sync_id": sync_id}
    finally:
        await conn.close()


async def fetch_detail(activity_id: str) -> dict[str, Any] | None:
    conn = await connect_db(_resolve_db_path())
    try:
        cached = await get_detail(conn, activity_id)
        if cached is not None:
            cached_dt = _parse_db_datetime(cached.get("fetched_at"))
            if cached_dt is not None and (_utc_now() - cached_dt) < timedelta(days=DETAIL_CACHE_TTL_DAYS):
                return _deserialize_detail_row(cached)

        client = get_activity_client()
        detail = await asyncio.to_thread(client.get_activity_detail, activity_id)
        detail_dict = detail.to_json_dict()
        stored_detail = {
            "samples": detail_dict.get("samples") or [],
            "track_points": detail_dict.get("track_points") or [],
            "raw_detail": detail_dict,
        }
        await upsert_detail(conn, activity_id, stored_detail)
        return stored_detail
    except Exception:
        logger.exception("Failed to fetch detail for %s", activity_id)
        return None
    finally:
        await conn.close()
