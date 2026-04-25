from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from portal.db import connect_db, init_db, log_sync_finish, log_sync_start
from portal.infrastructure import config
from portal.main import app


@pytest_asyncio.fixture
async def test_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "portal.db"
        state_path = Path(tmpdir) / "auth.json"
        monkeypatch.setattr(config, "DB_PATH", str(db_path))
        monkeypatch.setattr(config, "MI_FITNESS_STATE_PATH", str(state_path))
        await init_db(str(db_path))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, db_path


@pytest.mark.asyncio
async def test_sync_status_returns_list(test_client):
    client, db_path = test_client
    conn = await connect_db(str(db_path))
    try:
        sync_id = await log_sync_start(conn)
        await log_sync_finish(conn, sync_id, added=1, updated=0, error=None)
    finally:
        await conn.close()

    response = await client.get("/api/sync/status")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["syncs"]) == 1
    assert payload["syncs"][0]["activities_added"] == 1


@pytest.mark.asyncio
async def test_auth_status_when_not_authenticated(test_client):
    client, _ = test_client
    response = await client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "email": None,
        "expires_at": None,
    }


@pytest.mark.asyncio
async def test_activities_list_empty(test_client):
    client, _ = test_client
    response = await client.get("/api/activities")
    assert response.status_code == 200
    assert response.json() == {
        "activities": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }


@pytest.mark.asyncio
async def test_activities_list_includes_has_details_flag(test_client):
    client, db_path = test_client
    conn = await connect_db(str(db_path))
    try:
        await conn.execute(
            """
            INSERT INTO activities (activity_id, date, distance_km, synced_at)
            VALUES (?, ?, ?, ?)
            """,
            ("run-1", "2026-04-24T05:14:01+00:00", 3.17, "2026-04-24T13:21:22+00:00"),
        )
        await conn.execute(
            """
            INSERT INTO activity_details (activity_id, samples, track_points, raw_detail, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("run-1", "[]", "[]", "{}", "2026-04-24T13:21:22+00:00"),
        )
        await conn.commit()
    finally:
        await conn.close()

    response = await client.get("/api/activities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["activities"][0]["activity_id"] == "run-1"
    assert payload["activities"][0]["has_details"] is True


@pytest.mark.asyncio
async def test_activity_detail_page_renders_activity(test_client):
    client, db_path = test_client
    conn = await connect_db(str(db_path))
    try:
        await conn.execute(
            """
            INSERT INTO activities (activity_id, date, distance_km, synced_at)
            VALUES (?, ?, ?, ?)
            """,
            ("run-1", "2026-04-24T05:14:01+00:00", 3.17, "2026-04-24T13:21:22+00:00"),
        )
        await conn.commit()
    finally:
        await conn.close()

    response = await client.get("/activity/run-1")
    assert response.status_code == 200
    assert "Пробежка" in response.text
    assert "activity-data" in response.text


@pytest.mark.asyncio
async def test_load_all_activity_details_loads_only_missing(test_client, monkeypatch):
    client, db_path = test_client
    conn = await connect_db(str(db_path))
    try:
        await conn.execute(
            """
            INSERT INTO activities (activity_id, date, distance_km, synced_at)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                "run-1", "2026-04-24T05:14:01+00:00", 3.17, "2026-04-24T13:21:22+00:00",
                "run-2", "2026-04-23T05:14:01+00:00", 4.01, "2026-04-24T13:21:22+00:00",
            ),
        )
        await conn.execute(
            """
            INSERT INTO activity_details (activity_id, samples, track_points, raw_detail, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("run-1", "[]", "[]", "{}", "2026-04-24T13:21:22+00:00"),
        )
        await conn.commit()
    finally:
        await conn.close()

    from portal.routers import activities as activities_router

    calls: list[str] = []

    async def fake_fetch_detail(activity_id: str):
        calls.append(activity_id)
        return {"samples": [], "track_points": [], "raw_detail": {}}

    monkeypatch.setattr(activities_router, "fetch_detail", fake_fetch_detail)

    response = await client.post("/api/activities/details/load-all")
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["loaded"] == 1
    assert response.json()["failed"] == 0
    assert calls == ["run-2"]


@pytest.mark.asyncio
async def test_activities_progress_returns_weekly_ef(test_client):
    client, db_path = test_client
    conn = await connect_db(str(db_path))
    try:
        await conn.execute(
            """
            INSERT INTO activities (activity_id, date, distance_km, avg_pace, avg_hrm, synced_at)
            VALUES
            (?, ?, ?, ?, ?, ?),
            (?, ?, ?, ?, ?, ?),
            (?, ?, ?, ?, ?, ?),
            (?, ?, ?, ?, ?, ?),
            (?, ?, ?, ?, ?, ?),
            (?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1", "2026-03-31T05:14:01+00:00", 3.17, 360, 150, "2026-04-24T13:21:22+00:00",
                "run-2", "2026-04-02T05:14:01+00:00", 4.02, 350, 148, "2026-04-24T13:21:22+00:00",
                "run-3", "2026-04-07T05:14:01+00:00", 5.10, 345, 147, "2026-04-24T13:21:22+00:00",
                "run-4", "2026-04-14T05:14:01+00:00", 3.88, 340, 145, "2026-04-24T13:21:22+00:00",
                "run-5", "2026-04-21T05:14:01+00:00", 3.66, 338, 144, "2026-04-24T13:21:22+00:00",
                "run-6", "2026-04-28T05:14:01+00:00", 4.01, 336, 143, "2026-04-24T13:21:22+00:00",
            ),
        )
        await conn.commit()
    finally:
        await conn.close()

    response = await client.get("/api/activities/progress")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["weeks"]) >= 5
    assert payload["summary"]["first_ef"] > 0
    assert payload["summary"]["last_ef"] > 0
    assert payload["summary"]["max_ef"] >= payload["summary"]["first_ef"]
    assert payload["summary"]["total_weeks"] == len(payload["weeks"])
