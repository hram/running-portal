from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED

from portal.infrastructure import config


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_sync_lock = asyncio.Lock()

AUTO_SYNC_JOB_ID = "auto_sync"
MORNING_SYNC_JOB_ID = "morning_sync"


async def sync_activities() -> dict[str, object]:
    from portal.sync import sync_activities as run_sync_activities

    return await run_sync_activities()


async def generate_daily_recommendation(sync_id: int | None = None) -> dict[str, str]:
    from portal.routers.ai import generate_daily_recommendation as generate

    return await generate(sync_id=sync_id)


async def scheduled_sync() -> None:
    if _sync_lock.locked():
        logger.info("Scheduler: sync already running, skipping overlapping run")
        return

    async with _sync_lock:
        logger.info("Scheduler: starting scheduled sync")
        result = await sync_activities()
        changed = int(result.get("added", 0)) > 0 or int(result.get("updated", 0)) > 0
        if result.get("error") is None and changed:
            await generate_daily_recommendation(sync_id=result.get("sync_id"))
        logger.info("Scheduler: sync complete - %s", result)


def _parse_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        logger.warning("Invalid AUTO_SYNC_INTERVAL_HOURS=%r, using %s", value, default)
        return default
    if parsed < 0:
        logger.warning("AUTO_SYNC_INTERVAL_HOURS must be >= 0, using %s", default)
        return default
    return parsed


def _parse_time(value: str | None, default: str = "09:00") -> tuple[int, int]:
    raw = (value or default).strip()
    try:
        hour_raw, minute_raw = raw.split(":", 1)
        hour = int(hour_raw)
        minute = int(minute_raw)
    except ValueError:
        logger.warning("Invalid MORNING_SYNC_TIME=%r, using %s", value, default)
        return _parse_time(default)

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        logger.warning("MORNING_SYNC_TIME must be HH:MM, using %s", default)
        return _parse_time(default)
    return hour, minute


def configure_jobs() -> None:
    interval_hours = _parse_positive_int(config.AUTO_SYNC_INTERVAL_HOURS, default=1)
    if interval_hours > 0 and scheduler.get_job(AUTO_SYNC_JOB_ID) is None:
        scheduler.add_job(
            scheduled_sync,
            trigger="interval",
            hours=interval_hours,
            id=AUTO_SYNC_JOB_ID,
            replace_existing=True,
            misfire_grace_time=300,
            coalesce=True,
            max_instances=1,
        )

    if config.MORNING_SYNC_TIME and scheduler.get_job(MORNING_SYNC_JOB_ID) is None:
        hour, minute = _parse_time(config.MORNING_SYNC_TIME)
        scheduler.add_job(
            scheduled_sync,
            trigger="cron",
            hour=hour,
            minute=minute,
            id=MORNING_SYNC_JOB_ID,
            replace_existing=True,
            misfire_grace_time=900,
            coalesce=True,
            max_instances=1,
        )


def start() -> None:
    global scheduler
    if scheduler.state == STATE_STOPPED:
        scheduler = AsyncIOScheduler()
    configure_jobs()
    if scheduler.state != STATE_RUNNING:
        scheduler.start()
        logger.info(
            "Scheduler started, auto-sync every %s hour(s), morning sync at %s",
            config.AUTO_SYNC_INTERVAL_HOURS,
            config.MORNING_SYNC_TIME,
        )


def stop() -> None:
    if scheduler.state == STATE_RUNNING:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
