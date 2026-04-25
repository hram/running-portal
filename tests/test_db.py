from __future__ import annotations

import tempfile
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from portal.db import (
    connect_db,
    DEFAULT_SETTINGS,
    get_activities,
    get_activity,
    get_detail,
    get_ai_analysis,
    get_latest_recommendation,
    get_setting,
    get_settings,
    init_db,
    log_sync_finish,
    log_sync_start,
    save_recommendation,
    save_ai_analysis,
    save_setting,
    upsert_activity,
    upsert_detail,
)


@pytest_asyncio.fixture
async def conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        await init_db(str(db_path))
        connection = await connect_db(str(db_path))
        try:
            yield connection
        finally:
            await connection.close()


@pytest.mark.asyncio
async def test_init_db_creates_all_tables():
    async with aiosqlite.connect(":memory:") as conn:
        await conn.executescript("")
        await conn.executescript(
            """
            CREATE TABLE preexisting (id INTEGER PRIMARY KEY);
            """
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "schema.db"
        await init_db(str(db_path))
        async with aiosqlite.connect(str(db_path)) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
            names = {row[0] for row in await cursor.fetchall()}

    assert {"activities", "activity_details", "sync_log", "settings"}.issubset(names)


@pytest.mark.asyncio
async def test_upsert_activity_inserts_and_updates(conn):
    await upsert_activity(
        conn,
        {
            "activity_id": "run-1",
            "date": "2026-04-24T08:00:00Z",
            "distance_km": 5.2,
            "duration_seconds": 1800,
            "raw_report": {"source": "initial"},
        },
    )

    record = await get_activity(conn, "run-1")
    assert record is not None
    assert record["distance_km"] == 5.2

    await upsert_activity(
        conn,
        {
            "activity_id": "run-1",
            "date": "2026-04-24T08:00:00Z",
            "distance_km": 6.0,
            "duration_seconds": 1900,
            "raw_report": {"source": "updated"},
        },
    )

    updated = await get_activity(conn, "run-1")
    assert updated is not None
    assert updated["distance_km"] == 6.0
    assert '"updated"' in updated["raw_report"]


@pytest.mark.asyncio
async def test_upsert_detail_inserts_and_updates(conn):
    await upsert_activity(
        conn,
        {
            "activity_id": "run-1",
            "date": "2026-04-24T08:00:00Z",
        },
    )

    await upsert_detail(
        conn,
        "run-1",
        {
            "samples": [{"t": 1, "hr": 120}],
            "track_points": [{"lat": 1.0, "lon": 2.0}],
            "raw_detail": {"state": "initial"},
        },
    )

    record = await get_detail(conn, "run-1")
    assert record is not None
    assert '"initial"' in record["raw_detail"]

    await upsert_detail(
        conn,
        "run-1",
        {
            "samples": [{"t": 2, "hr": 125}],
            "track_points": [{"lat": 3.0, "lon": 4.0}],
            "raw_detail": {"state": "updated"},
        },
    )

    updated = await get_detail(conn, "run-1")
    assert updated is not None
    assert '"updated"' in updated["raw_detail"]


@pytest.mark.asyncio
async def test_get_activities_returns_paginated_list(conn):
    for idx in range(3):
        await upsert_activity(
            conn,
            {
                "activity_id": f"run-{idx}",
                "date": f"2026-04-2{idx}T08:00:00Z",
                "distance_km": float(idx),
            },
        )

    records = await get_activities(conn, limit=2, offset=0)
    assert [record["activity_id"] for record in records] == ["run-2", "run-1"]

    offset_records = await get_activities(conn, limit=2, offset=2)
    assert [record["activity_id"] for record in offset_records] == ["run-0"]


@pytest.mark.asyncio
async def test_get_activity_returns_one_record_or_none(conn):
    await upsert_activity(
        conn,
        {
            "activity_id": "run-1",
            "date": "2026-04-24T08:00:00Z",
        },
    )

    assert (await get_activity(conn, "run-1"))["activity_id"] == "run-1"
    assert await get_activity(conn, "missing") is None


@pytest.mark.asyncio
async def test_get_detail_returns_one_record_or_none(conn):
    await upsert_activity(
        conn,
        {
            "activity_id": "run-1",
            "date": "2026-04-24T08:00:00Z",
        },
    )
    await upsert_detail(conn, "run-1", {"raw_detail": {"ok": True}})

    assert (await get_detail(conn, "run-1"))["activity_id"] == "run-1"
    assert await get_detail(conn, "missing") is None


@pytest.mark.asyncio
async def test_log_sync_start_and_finish_write_sync_log(conn):
    sync_id = await log_sync_start(conn)
    await log_sync_finish(conn, sync_id, added=3, updated=2, error=None)

    cursor = await conn.execute(
        """
        SELECT started_at, finished_at, activities_added, activities_updated, error
        FROM sync_log
        WHERE id = ?
        """,
        (sync_id,),
    )
    row = await cursor.fetchone()

    assert row is not None
    assert row["started_at"]
    assert row["finished_at"]
    assert row["activities_added"] == 3
    assert row["activities_updated"] == 2
    assert row["error"] is None


@pytest.mark.asyncio
async def test_save_and_get_ai_analysis(conn):
    await upsert_activity(
        conn,
        {
            "activity_id": "run-ai",
            "date": "2026-04-24T08:00:00Z",
        },
    )
    await save_ai_analysis(conn, "run-ai", "Короткий AI анализ")

    analysis = await get_ai_analysis(conn, "run-ai")
    assert analysis == "Короткий AI анализ"


@pytest.mark.asyncio
async def test_get_ai_analysis_returns_none_if_missing(conn):
    assert await get_ai_analysis(conn, "missing") is None


@pytest.mark.asyncio
async def test_save_and_get_recommendation(conn):
    await save_recommendation(conn, "run", "Можно бежать", sync_id=None)
    await save_recommendation(conn, "rest", "Сегодня лучше отдых", sync_id=None)

    rec = await get_latest_recommendation(conn)
    assert rec is not None
    assert rec["status"] == "rest"
    assert rec["message"] == "Сегодня лучше отдых"


@pytest.mark.asyncio
async def test_get_latest_recommendation_returns_none_if_empty(conn):
    assert await get_latest_recommendation(conn) is None


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(conn):
    settings = await get_settings(conn)
    assert settings["daily_prompt_template"] == DEFAULT_SETTINGS["daily_prompt_template"]
    assert settings["activity_prompt_template"] == DEFAULT_SETTINGS["activity_prompt_template"]
    assert settings["target_hr_zone_low"] == "140"
    assert settings["target_hr_zone_high"] == "160"


@pytest.mark.asyncio
async def test_save_setting_updates_value(conn):
    await save_setting(conn, "target_hr_zone_low", "135")
    assert await get_setting(conn, "target_hr_zone_low") == "135"
