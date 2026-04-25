from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.base import STATE_RUNNING, STATE_STOPPED

from portal.sync import sync_activities


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def scheduled_sync() -> None:
    logger.info("Scheduler: starting scheduled sync")
    result = await sync_activities()
    logger.info("Scheduler: sync complete - %s", result)


def start() -> None:
    global scheduler
    if scheduler.state == STATE_STOPPED:
        scheduler = AsyncIOScheduler()
    if scheduler.get_job("auto_sync") is None:
        scheduler.add_job(
            scheduled_sync,
            trigger="interval",
            hours=1,
            id="auto_sync",
            replace_existing=True,
            misfire_grace_time=300,
        )
    if scheduler.state != STATE_RUNNING:
        scheduler.start()
        logger.info("Scheduler started, auto-sync every 1 hour")


def stop() -> None:
    if scheduler.state == STATE_RUNNING:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
