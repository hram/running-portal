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
