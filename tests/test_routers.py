from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from mi_fitness_sync.auth.state import AuthState
from mi_fitness_sync.auth.store import save_state
from mi_fitness_sync.exceptions import Step2RequiredError
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
async def test_sync_runs_recommendation_when_data_changed(test_client, monkeypatch):
    client, _ = test_client
    calls = []

    async def fake_sync_activities():
        return {"added": 0, "updated": 1, "total": 1, "error": None, "sync_id": 42}

    async def fake_generate_daily_recommendation(sync_id=None):
        calls.append(sync_id)
        return {"status": "rest", "message": "Сегодня отдых"}

    from portal.routers import sync as sync_router

    monkeypatch.setattr(sync_router, "sync_activities", fake_sync_activities)
    monkeypatch.setattr(sync_router, "generate_daily_recommendation", fake_generate_daily_recommendation)

    response = await client.post("/api/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation"] == {"status": "rest", "message": "Сегодня отдых"}
    assert calls == [42]


@pytest.mark.asyncio
async def test_sync_skips_recommendation_when_nothing_changed(test_client, monkeypatch):
    client, _ = test_client

    async def fake_sync_activities():
        return {"added": 0, "updated": 0, "total": 0, "error": None, "sync_id": 42}

    async def fake_generate_daily_recommendation(sync_id=None):
        raise AssertionError("recommendation should not run")

    from portal.routers import sync as sync_router

    monkeypatch.setattr(sync_router, "sync_activities", fake_sync_activities)
    monkeypatch.setattr(sync_router, "generate_daily_recommendation", fake_generate_daily_recommendation)

    response = await client.post("/api/sync")

    assert response.status_code == 200
    assert response.json()["recommendation"] is None


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
async def test_auth_login_reuses_existing_device_id(test_client, monkeypatch):
    client, _ = test_client
    state = AuthState(
        email="old@example.com",
        user_id="123",
        c_user_id="c-user",
        service_id="miothealth",
        pass_token="pass",
        service_token="service",
        ssecurity="security",
        psecurity=None,
        auto_login_url="https://example.com/sts",
        device_id="DEVICE-OLD",
        slh=None,
        ph=None,
        sts_cookie_header="",
        cookies=[],
        created_at="2026-04-24T00:00:00+00:00",
        updated_at="2026-04-24T00:00:00+00:00",
    )
    save_state(state, config.MI_FITNESS_STATE_PATH)
    captured = {}

    class DummySession:
        def to_auth_state(self):
            return state

    class DummyAuthClient:
        @staticmethod
        def generate_device_id():
            return "DEVICE-NEW"

        def login_with_password(self, *, email, password, device_id):
            captured["device_id"] = device_id
            return DummySession()

    from portal.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "get_auth_client", lambda: DummyAuthClient())

    response = await client.post("/api/auth/login", json={"email": "user@example.com", "password": "password"})

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert captured["device_id"] == "DEVICE-OLD"


@pytest.mark.asyncio
async def test_auth_login_returns_step2_verification_url(test_client, monkeypatch):
    client, _ = test_client

    class DummyAuthClient:
        @staticmethod
        def generate_device_id():
            return "DEVICE"

        def login_with_password(self, *, email, password, device_id):
            raise Step2RequiredError(
                "Xiaomi Passport requested a step-2 or interactive verification flow.",
                payload={"notificationUrl": "/pass/confirm"},
            )

    from portal.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "get_auth_client", lambda: DummyAuthClient())

    response = await client.post("/api/auth/login", json={"email": "user@example.com", "password": "password"})

    assert response.status_code == 200
    assert response.json() == {
        "success": False,
        "error": "Xiaomi Passport requested a step-2 or interactive verification flow.",
        "action": "verification",
        "verification_url": "https://account.xiaomi.com/pass/confirm",
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
    assert len(payload["scatter"]) == 6
    assert payload["scatter"][0]["month"]
    assert payload["scatter"][0]["month_label"]
