from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from portal.db import connect_db, get_detail, init_db, upsert_activity, upsert_detail
from portal.infrastructure import config
from portal.sync import AUTH_EXPIRED_MESSAGE, fetch_detail, get_last_sync_date, sync_activities
from mi_fitness_sync.activity.models import Activity
from mi_fitness_sync.exceptions import XiaomiApiError


def make_activity(
    *,
    activity_id: str,
    start_time: int,
    category: str = "running",
    distance_meters: int = 5000,
) -> Activity:
    return Activity(
        activity_id=activity_id,
        sid="sid",
        key="key",
        category=category,
        sport_type=1,
        title="Test Run",
        start_time=start_time,
        end_time=start_time + 1800,
        duration_seconds=1800,
        distance_meters=distance_meters,
        calories=300,
        steps=4000,
        sync_state="server",
        next_key=None,
        raw_record={"time": start_time, "category": category},
        raw_report={"distance": distance_meters, "duration": 1800},
    )


@dataclass
class FakeDetail:
    payload: dict

    def to_json_dict(self) -> dict:
        return self.payload


class FakeActivityClient:
    def __init__(self, activities=None, detail=None, error: Exception | None = None):
        self.activities = activities or []
        self.detail = detail
        self.error = error
        self.detail_calls = 0

    def list_activities(self, **_: object):
        if self.error is not None:
            raise self.error
        return self.activities

    def get_activity_detail(self, activity_id: str):
        self.detail_calls += 1
        if self.error is not None:
            raise self.error
        return self.detail or FakeDetail({"activity_id": activity_id, "samples": [], "track_points": []})


@pytest.fixture
def temp_db(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "portal.db"
        monkeypatch.setattr(config, "DB_PATH", str(db_path))
        yield db_path


@pytest.mark.asyncio
async def test_sync_activities_returns_correct_counts(temp_db):
    await init_db(str(temp_db))
    conn = await connect_db(str(temp_db))
    try:
        existing = make_activity(activity_id="existing", start_time=1713800000)
        await upsert_activity(
            conn,
            {
                "activity_id": existing.activity_id,
                "date": "2026-04-20T10:00:00+00:00",
                "distance_km": 5.0,
            },
        )
    finally:
        await conn.close()

    client = FakeActivityClient(
        activities=[
            make_activity(activity_id="existing", start_time=1713800000),
            make_activity(activity_id="new-run", start_time=1713810000),
            make_activity(activity_id="walk", start_time=1713820000, category="walking"),
            make_activity(activity_id="short", start_time=1713830000, distance_meters=200),
        ]
    )

    with patch("portal.sync.get_activity_client", return_value=client):
        result = await sync_activities()

    assert result["added"] == 1
    assert result["updated"] == 1
    assert result["total"] == 2
    assert result["details_loaded"] == 1
    assert result["error"] is None
    assert isinstance(result["sync_id"], int)
    assert client.detail_calls == 1

    conn = await connect_db(str(temp_db))
    try:
        detail = await get_detail(conn, "new-run")
    finally:
        await conn.close()

    assert detail is not None


@pytest.mark.asyncio
async def test_sync_activities_handles_error(temp_db):
    await init_db(str(temp_db))
    client = FakeActivityClient(error=RuntimeError("boom"))

    with patch("portal.sync.get_activity_client", return_value=client):
        result = await sync_activities()

    assert result["added"] == 0
    assert result["updated"] == 0
    assert result["total"] == 0
    assert result["error"] == "boom"

    conn = await connect_db(str(temp_db))
    try:
        cursor = await conn.execute("SELECT error FROM sync_log ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
    finally:
        await conn.close()

    assert row is not None
    assert row["error"] == "boom"


@pytest.mark.asyncio
async def test_sync_activities_refreshes_auth_state_on_401(temp_db):
    await init_db(str(temp_db))
    first_client = FakeActivityClient(error=XiaomiApiError("auth rejected", code=401))
    refreshed_client = FakeActivityClient(
        activities=[make_activity(activity_id="new-run", start_time=1713810000)]
    )

    with (
        patch("portal.sync.get_activity_client", side_effect=[first_client, refreshed_client, refreshed_client]),
        patch("portal.sync.refresh_auth_state", return_value=object()) as refresh_mock,
    ):
        result = await sync_activities()

    assert result["added"] == 1
    assert result["updated"] == 0
    assert result["total"] == 1
    assert result["details_loaded"] == 1
    assert result["error"] is None
    refresh_mock.assert_called_once_with()


@pytest.mark.asyncio
async def test_sync_activities_skips_auto_detail_when_multiple_activities_added(temp_db):
    await init_db(str(temp_db))
    client = FakeActivityClient(
        activities=[
            make_activity(activity_id="new-run-1", start_time=1713810000),
            make_activity(activity_id="new-run-2", start_time=1713820000),
        ]
    )

    with patch("portal.sync.get_activity_client", return_value=client):
        result = await sync_activities()

    assert result["added"] == 2
    assert result["details_loaded"] == 0
    assert client.detail_calls == 0


@pytest.mark.asyncio
async def test_sync_activities_clears_auth_state_when_refresh_fails(temp_db, monkeypatch):
    await init_db(str(temp_db))
    state_path = temp_db.parent / "auth.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "MI_FITNESS_STATE_PATH", str(state_path))
    client = FakeActivityClient(error=XiaomiApiError("auth rejected", code=401))

    with (
        patch("portal.sync.get_activity_client", return_value=client),
        patch("portal.sync.refresh_auth_state", side_effect=XiaomiApiError("refresh failed", code=401)),
    ):
        result = await sync_activities()

    assert result["error"] == AUTH_EXPIRED_MESSAGE
    assert not state_path.exists()

    conn = await connect_db(str(temp_db))
    try:
        cursor = await conn.execute("SELECT error FROM sync_log ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
    finally:
        await conn.close()

    assert row is not None
    assert row["error"] == AUTH_EXPIRED_MESSAGE


@pytest.mark.asyncio
async def test_fetch_detail_uses_cache(temp_db):
    await init_db(str(temp_db))
    conn = await connect_db(str(temp_db))
    try:
        await upsert_activity(
            conn,
            {
                "activity_id": "run-1",
                "date": "2026-04-24T08:00:00+00:00",
            },
        )
        await upsert_detail(
            conn,
            "run-1",
            {
                "samples": [{"timestamp": 1}],
                "track_points": [{"timestamp": 2}],
                "raw_detail": {"cached": True},
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        await conn.close()

    with patch("portal.sync.get_activity_client", side_effect=AssertionError("network call should not happen")):
        detail = await fetch_detail("run-1")

    assert detail is not None
    assert detail["raw_detail"]["cached"] is True
    assert detail["samples"] == [{"timestamp": 1}]


@pytest.mark.asyncio
async def test_get_last_sync_date_returns_none_for_empty_db(temp_db):
    await init_db(str(temp_db))
    conn = await connect_db(str(temp_db))
    try:
        result = await get_last_sync_date(conn)
    finally:
        await conn.close()

    assert result is None


@pytest.mark.asyncio
async def test_get_last_sync_date_returns_latest_date(temp_db):
    await init_db(str(temp_db))
    conn = await connect_db(str(temp_db))
    try:
        await upsert_activity(conn, {"activity_id": "old", "date": "2026-04-20T08:00:00+00:00"})
        await upsert_activity(conn, {"activity_id": "new", "date": "2026-04-22T08:00:00+00:00"})
        result = await get_last_sync_date(conn)
    finally:
        await conn.close()

    assert result == datetime(2026, 4, 22, 8, 0, tzinfo=timezone.utc)
