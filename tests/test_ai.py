from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from portal.db import connect_db, init_db, save_ai_analysis
from portal.db import get_latest_recommendation
from portal.db import save_recommendation
from portal.infrastructure import config
from portal.main import app
from portal.routers.ai import build_daily_prompt, build_prompt, generate_goal_suggestion


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
async def test_get_activity_analysis_prompt(ai_client):
    client, db_path = ai_client
    conn = await connect_db(str(db_path))
    try:
        await conn.execute(
            """
            INSERT INTO health_states (description, started_at, ended_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Болит левое колено", "2026-05-24", None, "2026-05-24T10:00:00", "2026-05-24T10:00:00"),
        )
        await conn.commit()
    finally:
        await conn.close()

    response = await client.get("/api/ai/analyze/prompt", params={"activity_id": "run-ai"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["activity_id"] == "run-ai"
    assert "Последние записи о здоровье" in payload["prompt"]
    assert "Болит левое колено" in payload["prompt"]


@pytest.mark.asyncio
async def test_analyze_returns_404_for_unknown_activity(ai_client):
    client, _ = ai_client
    response = await client.post("/api/ai/analyze", json={"activity_id": "missing", "force_refresh": False})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_activity_analysis_prompt_returns_404_for_unknown_activity(ai_client):
    client, _ = ai_client
    response = await client.get("/api/ai/analyze/prompt", params={"activity_id": "missing"})
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


@pytest.mark.asyncio
async def test_refresh_recommendation_reports_claude_auth_error(ai_client, monkeypatch):
    client, db_path = ai_client

    class FakeProcess:
        stdout = io.StringIO(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Failed to authenticate: OAuth session expired and could not be refreshed",
                                    }
                                ]
                            },
                            "is_error": True,
                        }
                    ),
                    json.dumps(
                        {
                            "type": "result",
                            "is_error": True,
                            "result": "Failed to authenticate: OAuth session expired and could not be refreshed",
                        }
                    ),
                ]
            )
        )
        stderr = io.StringIO("")

        def wait(self) -> int:
            return 1

    from portal.routers import ai as ai_router

    monkeypatch.setattr(ai_router.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    response = await client.post("/api/ai/recommendation/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert "OAuth session expired" in payload["message"]

    conn = await connect_db(str(db_path))
    try:
        assert await get_latest_recommendation(conn) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_recommendation_prompt(ai_client):
    client, db_path = ai_client
    conn = await connect_db(str(db_path))
    try:
        await save_ai_analysis(conn, "run-ai", "Не бегать 5-7 дней из-за боли в колене")
        await conn.execute(
            """
            INSERT INTO health_states (description, started_at, ended_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Болит левое колено", "2026-05-24", None, "2026-05-24T10:00:00", "2026-05-24T10:00:00"),
        )
        await conn.commit()
    finally:
        await conn.close()

    response = await client.get("/api/ai/recommendation/prompt")

    assert response.status_code == 200
    prompt = response.json()["prompt"]
    assert "Последняя пробежка" in prompt
    assert "Болит левое колено" in prompt
    assert "Не бегать 5-7 дней" in prompt


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(ai_client):
    client, _ = ai_client
    response = await client.get("/api/settings")
    assert response.status_code == 200
    payload = response.json()
    assert payload["target_hr_zone_low"] == "140"
    assert payload["target_hr_zone_high"] == "160"
    assert payload["dashboard_card_progress"] == "true"
    assert "{health_lines}" in payload["daily_prompt_template"]
    assert "{last_activity_analysis}" in payload["daily_prompt_template"]
    assert "Ты персональный тренер" in payload["daily_prompt_template"]


@pytest.mark.asyncio
async def test_post_settings_updates_values(ai_client):
    client, _ = ai_client
    response = await client.post(
        "/api/settings",
        json={
            "daily_prompt_template": "daily {hours_since}",
            "activity_prompt_template": "activity {activity_date}",
            "target_hr_zone_low": 135,
            "target_hr_zone_high": 165,
            "dashboard_card_progress": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["settings"]["daily_prompt_template"] == "daily {hours_since}"
    assert payload["settings"]["activity_prompt_template"] == "activity {activity_date}"
    assert payload["settings"]["target_hr_zone_low"] == "135"
    assert payload["settings"]["target_hr_zone_high"] == "165"
    assert payload["settings"]["dashboard_card_progress"] == "false"


def test_build_prompt_includes_latest_health_states():
    activity = {
        "date": "2026-05-24T05:14:01+00:00",
        "distance_km": 3.17,
        "avg_hrm": 150,
        "avg_pace": 360,
        "avg_cadence": 170,
        "avg_stride": 90,
        "train_load": 80,
        "recover_time": 12,
    }
    settings = {"activity_prompt_template": "Пробежка {activity_date}\n{recent_lines}"}
    health_states = [
        {"started_at": "2026-05-24", "ended_at": None, "description": "Болит левое колено"},
        {"started_at": "2026-05-20", "ended_at": "2026-05-22", "description": "Тянула спина"},
        {"started_at": "2026-05-17", "ended_at": "2026-05-18", "description": "Болели стопы"},
        {"started_at": "2026-05-10", "ended_at": "2026-05-11", "description": "Старая запись"},
    ]

    prompt = build_prompt(activity, [activity], settings, health_states, current_date="2026-05-24")

    assert "Текущая дата: 2026-05-24" in prompt
    assert "Последние записи о здоровье" in prompt
    assert "1. Период: 2026-05-24 — сейчас" in prompt
    assert "   Описание:\n    Болит левое колено" in prompt
    assert "Болит левое колено" in prompt
    assert "Тянула спина" in prompt
    assert "Болели стопы" in prompt
    assert "Старая запись" not in prompt


def test_build_daily_prompt_includes_health_and_last_analysis():
    activity = {
        "activity_id": "run-ai",
        "date": "2026-05-24T05:14:01+00:00",
        "distance_km": 3.17,
        "avg_hrm": 150,
        "avg_pace": 360,
        "train_load": 80,
        "recover_time": 12,
    }
    settings = {
        "daily_prompt_template": (
            "Сегодня {current_date}\n"
            "{recent_lines}\n"
            "Здоровье:\n{health_lines}\n"
            "Анализ:\n{last_activity_analysis}"
        )
    }

    prompt = build_daily_prompt(
        [activity],
        settings,
        health_states=[{"started_at": "2026-05-24", "ended_at": None, "description": "Болит левое колено"}],
        last_activity_analysis="Не бегать 5-7 дней",
        current_date="2026-05-25",
    )

    assert "Сегодня 2026-05-25" in prompt
    assert "Болит левое колено" in prompt
    assert "Не бегать 5-7 дней" in prompt


@pytest.mark.asyncio
async def test_generate_goal_suggestion_returns_history_based_fallback(monkeypatch):
    def fake_popen(*args, **kwargs):
        raise FileNotFoundError("claude missing")

    from portal.routers import ai as ai_router

    monkeypatch.setattr(ai_router.subprocess, "Popen", fake_popen)

    result = await generate_goal_suggestion(
        [
            {"date": "2026-04-24T08:00:00+00:00", "distance_km": 5.0, "avg_hrm": 150, "train_load": 80},
            {"date": "2026-04-20T08:00:00+00:00", "distance_km": 6.0, "avg_hrm": 152, "train_load": 90},
        ],
        2026,
        5,
    )

    assert result["km_goal"] > 0
    assert result["runs_goal"] > 0
    assert result["reasoning"] == "fallback_after_error"
    assert "AI-анализ сейчас недоступен" in result["message"]
