from __future__ import annotations

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from portal import scheduler


@pytest.mark.asyncio
async def test_scheduled_sync_runs_recommendation_when_data_changed(monkeypatch):
    calls = []

    async def fake_sync_activities():
        return {"added": 0, "updated": 1, "error": None, "sync_id": 42}

    async def fake_generate_daily_recommendation(sync_id=None):
        calls.append(sync_id)
        return {"status": "rest", "message": "Сегодня отдых"}

    monkeypatch.setattr(scheduler, "sync_activities", fake_sync_activities)
    monkeypatch.setattr(scheduler, "generate_daily_recommendation", fake_generate_daily_recommendation)

    await scheduler.scheduled_sync()

    assert calls == [42]


@pytest.mark.asyncio
async def test_scheduled_sync_skips_recommendation_when_nothing_changed(monkeypatch):
    async def fake_sync_activities():
        return {"added": 0, "updated": 0, "error": None, "sync_id": 42}

    async def fake_generate_daily_recommendation(sync_id=None):
        raise AssertionError("recommendation should not run")

    monkeypatch.setattr(scheduler, "sync_activities", fake_sync_activities)
    monkeypatch.setattr(scheduler, "generate_daily_recommendation", fake_generate_daily_recommendation)

    await scheduler.scheduled_sync()


def test_configure_jobs_adds_hourly_and_morning_sync(monkeypatch):
    test_scheduler = AsyncIOScheduler()
    monkeypatch.setattr(scheduler, "scheduler", test_scheduler)
    monkeypatch.setattr(scheduler.config, "AUTO_SYNC_INTERVAL_HOURS", "1")
    monkeypatch.setattr(scheduler.config, "MORNING_SYNC_TIME", "09:15")

    scheduler.configure_jobs()

    jobs = {job.id: job for job in test_scheduler.get_jobs()}
    assert set(jobs) == {scheduler.AUTO_SYNC_JOB_ID, scheduler.MORNING_SYNC_JOB_ID}
    assert str(jobs[scheduler.AUTO_SYNC_JOB_ID].trigger) == "interval[1:00:00]"
    assert "hour='9'" in str(jobs[scheduler.MORNING_SYNC_JOB_ID].trigger)
    assert "minute='15'" in str(jobs[scheduler.MORNING_SYNC_JOB_ID].trigger)


def test_configure_jobs_can_disable_hourly_sync(monkeypatch):
    test_scheduler = AsyncIOScheduler()
    monkeypatch.setattr(scheduler, "scheduler", test_scheduler)
    monkeypatch.setattr(scheduler.config, "AUTO_SYNC_INTERVAL_HOURS", "0")
    monkeypatch.setattr(scheduler.config, "MORNING_SYNC_TIME", "09:00")

    scheduler.configure_jobs()

    jobs = {job.id for job in test_scheduler.get_jobs()}
    assert jobs == {scheduler.MORNING_SYNC_JOB_ID}
