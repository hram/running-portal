from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    activity_id     TEXT PRIMARY KEY,
    date            TEXT NOT NULL,
    distance_km     REAL,
    duration_seconds INTEGER,
    avg_hrm         INTEGER,
    avg_pace        INTEGER,
    avg_cadence     INTEGER,
    avg_stride      INTEGER,
    train_load      INTEGER,
    recover_time    INTEGER,
    vo2_max         INTEGER,
    aerobic_train_effect  REAL,
    anaerobic_train_effect REAL,
    hrm_warm_up_duration      INTEGER,
    hrm_fat_burning_duration  INTEGER,
    hrm_aerobic_duration      INTEGER,
    hrm_anaerobic_duration    INTEGER,
    hrm_extreme_duration      INTEGER,
    avg_vertical_stride_ratio REAL,
    avg_touchdown_duration    INTEGER,
    avg_vertical_amplitude    REAL,
    raw_report      TEXT,
    synced_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_details (
    activity_id  TEXT PRIMARY KEY,
    samples      TEXT,
    track_points TEXT,
    raw_detail   TEXT,
    fetched_at   TEXT NOT NULL,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    activities_added   INTEGER DEFAULT 0,
    activities_updated INTEGER DEFAULT 0,
    error           TEXT
);

CREATE TABLE IF NOT EXISTS ai_analysis (
    activity_id  TEXT PRIMARY KEY,
    analysis     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (activity_id) REFERENCES activities(activity_id)
);

CREATE TABLE IF NOT EXISTS daily_recommendation (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    status       TEXT NOT NULL,
    message      TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    sync_id      INTEGER,
    FOREIGN KEY (sync_id) REFERENCES sync_log(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, str] = {
    "daily_prompt_template": """Ты персональный тренер по бегу. Отвечай строго в формате JSON.

Бегун восстанавливается после травмы ступней. Цель: войти в ритм, бегать регулярно.
Новые кроссовки 361 KAIROS 2 — первые недели в них.

Последняя пробежка: {last_date}, {last_distance_km}км,
пульс {last_avg_hrm} уд/мин, темп {last_avg_pace},
нагрузка {last_train_load}, восстановление {last_recover_time}ч.
С последней пробежки прошло: {hours_since} часов.

Последние 7 пробежек:
{recent_lines}

Ответь ТОЛЬКО валидным JSON без markdown, без пояснений:
{{
  "status": "run" | "run_easy" | "rest",
  "message": "два предложения — анализ ситуации и конкретная рекомендация на сегодня"
}}

Критерии выбора status:
- "rest": recover_time последней пробежки ещё не истёк (часов прошло < recover_time) ИЛИ пульс был > 185
- "run_easy": пульс был 170–185 ИЛИ нагрузка > 200 ИЛИ recover_time почти истёк
- "run": всё в норме, можно бежать в обычном режиме""",
    "activity_prompt_template": """Ты персональный тренер по бегу. Говори коротко и по-русски, как живой тренер — без воды. Пиши связным текстом, 3–5 предложений.

Бегун восстанавливается после травмы ступней и голеностопа. Цель: войти в ритм, бегать регулярно. Недавно купил новые кроссовки 361 KAIROS 2 (стек 34мм, перепад 8мм) — первые недели в них.

Пробежка {activity_date}:
- Дистанция: {activity_distance_km} км
- Пульс: {activity_avg_hrm} уд/мин
- Темп: {activity_avg_pace}
- Каденс: {activity_avg_cadence} ш/мин
- Длина шага: {activity_avg_stride} см
- Нагрузка: {activity_train_load}
- Восстановление: {activity_recover_time} ч
- Пульсовые зоны: {activity_zones}

Последние 10 пробежек:
{recent_lines}

Дай короткий анализ этой пробежки и одну конкретную рекомендацию на следующую тренировку.""",
    "target_hr_zone_low": "140",
    "target_hr_zone_high": "160",
}

ACTIVITY_COLUMNS = (
    "activity_id",
    "date",
    "distance_km",
    "duration_seconds",
    "avg_hrm",
    "avg_pace",
    "avg_cadence",
    "avg_stride",
    "train_load",
    "recover_time",
    "vo2_max",
    "aerobic_train_effect",
    "anaerobic_train_effect",
    "hrm_warm_up_duration",
    "hrm_fat_burning_duration",
    "hrm_aerobic_duration",
    "hrm_anaerobic_duration",
    "hrm_extreme_duration",
    "avg_vertical_stride_ratio",
    "avg_touchdown_duration",
    "avg_vertical_amplitude",
    "raw_report",
    "synced_at",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_db_path(db_path: str) -> str:
    return str(Path(db_path).expanduser())


def _serialize_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


async def init_db(db_path: str) -> None:
    normalized_path = normalize_db_path(db_path)
    async with aiosqlite.connect(normalized_path) as conn:
        await conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            await conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, value, utc_now_iso()),
            )
        await conn.commit()


async def connect_db(db_path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(normalize_db_path(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn


async def upsert_activity(conn: aiosqlite.Connection, activity_dict: dict[str, Any]) -> None:
    payload = {column: activity_dict.get(column) for column in ACTIVITY_COLUMNS}
    payload["raw_report"] = _serialize_json(payload.get("raw_report"))
    payload["synced_at"] = payload.get("synced_at") or utc_now_iso()
    placeholders = ", ".join(f":{column}" for column in ACTIVITY_COLUMNS)
    columns = ", ".join(ACTIVITY_COLUMNS)
    await conn.execute(
        f"INSERT OR REPLACE INTO activities ({columns}) VALUES ({placeholders})",
        payload,
    )
    await conn.commit()


async def upsert_detail(conn: aiosqlite.Connection, activity_id: str, detail_dict: dict[str, Any]) -> None:
    payload = {
        "activity_id": activity_id,
        "samples": _serialize_json(detail_dict.get("samples")),
        "track_points": _serialize_json(detail_dict.get("track_points")),
        "raw_detail": _serialize_json(detail_dict.get("raw_detail")),
        "fetched_at": detail_dict.get("fetched_at") or utc_now_iso(),
    }
    await conn.execute(
        """
        INSERT OR REPLACE INTO activity_details (
            activity_id,
            samples,
            track_points,
            raw_detail,
            fetched_at
        ) VALUES (
            :activity_id,
            :samples,
            :track_points,
            :raw_detail,
            :fetched_at
        )
        """,
        payload,
    )
    await conn.commit()


async def get_activities(conn: aiosqlite.Connection, limit: int, offset: int) -> list[dict[str, Any]]:
    cursor = await conn.execute(
        """
        SELECT * FROM activities
        ORDER BY date DESC, activity_id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_activity_count(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute("SELECT COUNT(*) AS count FROM activities")
    row = await cursor.fetchone()
    return int(row["count"] if row is not None else 0)


async def get_activities_for_ef(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await conn.execute(
        """
        SELECT date, avg_pace, avg_hrm, distance_km
        FROM activities
        WHERE avg_pace IS NOT NULL
          AND avg_pace > 0
          AND avg_hrm IS NOT NULL
          AND avg_hrm > 0
          AND distance_km > 0.3
        ORDER BY date ASC
        """
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_activity(conn: aiosqlite.Connection, activity_id: str) -> dict[str, Any] | None:
    cursor = await conn.execute("SELECT * FROM activities WHERE activity_id = ?", (activity_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_detail(conn: aiosqlite.Connection, activity_id: str) -> dict[str, Any] | None:
    cursor = await conn.execute("SELECT * FROM activity_details WHERE activity_id = ?", (activity_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_recent_sync_logs(conn: aiosqlite.Connection, limit: int = 5) -> list[dict[str, Any]]:
    cursor = await conn.execute(
        """
        SELECT * FROM sync_log
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def log_sync_start(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute(
        "INSERT INTO sync_log (started_at) VALUES (?)",
        (utc_now_iso(),),
    )
    await conn.commit()
    return int(cursor.lastrowid)


async def log_sync_finish(
    conn: aiosqlite.Connection,
    sync_id: int,
    added: int,
    updated: int,
    error: str | None,
) -> None:
    await conn.execute(
        """
        UPDATE sync_log
        SET finished_at = ?,
            activities_added = ?,
            activities_updated = ?,
            error = ?
        WHERE id = ?
        """,
        (utc_now_iso(), added, updated, error, sync_id),
    )
    await conn.commit()


async def get_ai_analysis(conn: aiosqlite.Connection, activity_id: str) -> str | None:
    cursor = await conn.execute(
        "SELECT analysis FROM ai_analysis WHERE activity_id = ?",
        (activity_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return str(row["analysis"])


async def save_ai_analysis(conn: aiosqlite.Connection, activity_id: str, analysis: str) -> None:
    await conn.execute(
        """
        INSERT OR REPLACE INTO ai_analysis (activity_id, analysis, created_at)
        VALUES (?, ?, ?)
        """,
        (activity_id, analysis, utc_now_iso()),
    )
    await conn.commit()


async def get_latest_recommendation(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    cursor = await conn.execute(
        """
        SELECT * FROM daily_recommendation
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def save_recommendation(
    conn: aiosqlite.Connection,
    status: str,
    message: str,
    sync_id: int | None = None,
) -> None:
    now = utc_now_iso()
    await conn.execute(
        """
        INSERT INTO daily_recommendation (date, status, message, generated_at, sync_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now[:10], status, message, now, sync_id),
    )
    await conn.commit()


async def get_setting(conn: aiosqlite.Connection, key: str) -> str | None:
    cursor = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return str(row["value"])


async def get_settings(conn: aiosqlite.Connection) -> dict[str, str]:
    cursor = await conn.execute("SELECT key, value FROM settings ORDER BY key")
    rows = await cursor.fetchall()
    settings = {row["key"]: str(row["value"]) for row in rows}
    return {**DEFAULT_SETTINGS, **settings}


async def save_setting(conn: aiosqlite.Connection, key: str, value: str) -> None:
    await conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, value, utc_now_iso()),
    )
    await conn.commit()
