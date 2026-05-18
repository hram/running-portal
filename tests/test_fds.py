from __future__ import annotations

from unittest.mock import MagicMock

from mi_fitness_sync.activity.fds import ActivityFdsService
from mi_fitness_sync.activity.models import Activity
from mi_fitness_sync.activity.utils import build_fds_suffix


def make_activity(
    *,
    record_time: int = 1779080864,
    report_time: int | None = 1779080863,
) -> Activity:
    raw_report = {
        "proto_type": 22,
        "timezone": 12,
    }
    if report_time is not None:
        raw_report["time"] = report_time

    return Activity(
        activity_id=f"986361512:outdoor_running:{record_time}",
        sid="986361512",
        key="outdoor_running",
        category="running",
        sport_type=1,
        title="Test Run",
        start_time=record_time,
        end_time=record_time + 1599,
        duration_seconds=1599,
        distance_meters=3653,
        calories=148,
        steps=4206,
        sync_state="server",
        next_key=None,
        raw_record={"sid": "986361512", "key": "outdoor_running", "time": record_time},
        raw_report=raw_report,
    )


def make_service() -> ActivityFdsService:
    return ActivityFdsService(
        session=MagicMock(),
        transport=MagicMock(),
        timeout=10,
        cache=None,
    )


def test_fds_context_uses_report_time_when_record_time_differs():
    activity = make_activity(record_time=1779080864, report_time=1779080863)
    service = make_service()

    context = service._build_context(activity)

    assert context is not None
    assert context.timestamp == 1779080863


def test_fds_context_falls_back_to_start_time_without_report_time():
    activity = make_activity(record_time=1779080864, report_time=None)
    service = make_service()

    context = service._build_context(activity)

    assert context is not None
    assert context.timestamp == activity.start_time


def test_fds_request_suffix_uses_report_time():
    activity = make_activity(record_time=1779080864, report_time=1779080863)
    service = make_service()

    context = service._build_context(activity)
    assert context is not None
    item = service._build_request_item(context, file_type=0)

    expected_suffix = build_fds_suffix(
        sid=activity.sid,
        timestamp=1779080863,
        timezone_offset=12,
        sport_type=22,
        file_type=0,
    )
    wrong_suffix = build_fds_suffix(
        sid=activity.sid,
        timestamp=1779080864,
        timezone_offset=12,
        sport_type=22,
        file_type=0,
    )

    assert item == {"timestamp": 1779080863, "suffix": expected_suffix}
    assert item["suffix"] != wrong_suffix
