from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from portal.db import connect_db, init_db, save_ai_analysis
from portal.db import save_recommendation
from portal.infrastructure import config
from portal.main import app


@pytest_asyncio.fixture
async def ai_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "portal.db"
        monkeypatch.setattr(config, "DB_PATH", str(db_path))
        await init_db(str(db_path))

        conn = await connect_db(str(db_path))
        try:
            await conn.execute(
                """
                INSERT INTO activities (activity_id, date, distance_km, synced_at)
                VALUES (?, ?, ?, ?)
                """,
                ("run-ai", "2026-04-24T05:14:01+00:00", 3.17, "2026-04-24T13:21:22+00:00"),
            )
            await conn.commit()
        finally:
            await conn.close()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, db_path


@pytest.mark.asyncio
async def test_analyze_returns_cached_result(ai_client):
    client, db_path = ai_client
    conn = await connect_db(str(db_path))
    try:
        await save_ai_analysis(conn, "run-ai", "cached text")
    finally:
        await conn.close()

    response = await client.post("/api/ai/analyze", json={"activity_id": "run-ai", "force_refresh": False})
    assert response.status_code == 200
    assert response.json() == {
        "analysis": "cached text",
        "cached": True,
        "activity_id": "run-ai",
    }


@pytest.mark.asyncio
async def test_analyze_returns_stream_url_when_no_cache(ai_client):
    client, _ = ai_client
    response = await client.post("/api/ai/analyze", json={"activity_id": "run-ai", "force_refresh": False})
    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"] is None
    assert payload["cached"] is False
    assert payload["stream_url"] == "/api/ai/analyze/stream?activity_id=run-ai"


@pytest.mark.asyncio
async def test_analyze_returns_404_for_unknown_activity(ai_client):
    client, _ = ai_client
    response = await client.post("/api/ai/analyze", json={"activity_id": "missing", "force_refresh": False})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_recommendation_returns_none_when_empty(ai_client):
    client, _ = ai_client
    response = await client.get("/api/ai/recommendation")
    assert response.status_code == 200
    assert response.json() == {"status": None, "message": None, "generated_at": None}


@pytest.mark.asyncio
async def test_get_recommendation_returns_latest(ai_client):
    client, db_path = ai_client
    conn = await connect_db(str(db_path))
    try:
        await save_recommendation(conn, "run_easy", "Сегодня только лёгкий бег")
    finally:
        await conn.close()

    response = await client.get("/api/ai/recommendation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "run_easy"
    assert payload["message"] == "Сегодня только лёгкий бег"
