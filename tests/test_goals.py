from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from portal.db import connect_db, init_db, save_monthly_goal, upsert_activity
from portal.infrastructure import config
from portal.main import app
from portal.routers.goals import build_goal_payload


@pytest_asyncio.fixture
async def goals_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "portal.db"
        monkeypatch.setattr(config, "DB_PATH", str(db_path))
        await init_db(str(db_path))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, db_path


def test_build_goal_payload_marks_goal_statuses():
    goal = {"km_goal": 100.0, "runs_goal": 10}

    on_track = build_goal_payload(goal, {"total_km": 100.0, "runs_count": 10}, 2026, 1)
    behind = build_goal_payload(goal, {"total_km": 1.0, "runs_count": 0}, 2026, 1)

    assert on_track["status"] == "on_track"
    assert behind["status"] == "behind"
    assert behind["km_remaining"] == 99.0
    assert behind["runs_remaining"] == 10


@pytest.mark.asyncio
async def test_get_monthly_goal_returns_no_goal_payload(goals_client):
    client, _ = goals_client

    response = await client.get("/api/goals/monthly?year=2026&month=4")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "no_goal"
    assert payload["goal"] is None
    assert payload["progress"] == {"runs_count": 0, "total_km": 0.0}


@pytest.mark.asyncio
async def test_set_and_get_monthly_goal_with_progress(goals_client):
    client, db_path = goals_client
    conn = await connect_db(str(db_path))
    try:
        await upsert_activity(conn, {"activity_id": "run-1", "date": "2026-04-05T08:00:00+00:00", "distance_km": 5.0})
        await upsert_activity(conn, {"activity_id": "run-2", "date": "2026-04-10T08:00:00+00:00", "distance_km": 6.5})
    finally:
        await conn.close()

    response = await client.post(
        "/api/goals/monthly",
        json={"year": 2026, "month": 4, "km_goal": 50.0, "runs_goal": 12, "ai_suggestion": "steady"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["goal"]["km_goal"] == 50.0
    assert payload["goal"]["runs_goal"] == 12
    assert payload["goal"]["ai_suggestion"] == "steady"
    assert payload["progress"] == {"runs_count": 2, "total_km": 11.5}
    assert payload["km_remaining"] == 38.5


@pytest.mark.asyncio
async def test_suggest_monthly_goal_uses_ai_helper(goals_client, monkeypatch):
    client, db_path = goals_client
    conn = await connect_db(str(db_path))
    try:
        await upsert_activity(conn, {"activity_id": "run-1", "date": "2026-04-05T08:00:00+00:00", "distance_km": 5.0})
    finally:
        await conn.close()

    async def fake_generate_goal_suggestion(activities, year, month):
        return {
            "km_goal": 45.0,
            "runs_goal": 11,
            "message": f"{len(activities)} runs for {year}-{month}",
            "conservative": {"km_goal": 38.0, "runs_goal": 9},
            "ambitious": {"km_goal": 52.0, "runs_goal": 13},
        }

    from portal.routers import goals as goals_router

    monkeypatch.setattr(goals_router, "generate_goal_suggestion", fake_generate_goal_suggestion)

    response = await client.get("/api/goals/monthly/suggest?year=2026&month=5")

    assert response.status_code == 200
    assert response.json()["message"] == "1 runs for 2026-5"
