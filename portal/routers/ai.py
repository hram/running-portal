from __future__ import annotations

import asyncio
import json
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from portal.db import (
    connect_db,
    get_activities,
    get_activity,
    get_ai_analysis,
    get_latest_recommendation,
    save_ai_analysis,
    save_recommendation,
)
from portal.infrastructure import config
from portal.sync import _resolve_db_path


router = APIRouter()


class AnalyzeRequest(BaseModel):
    activity_id: str
    force_refresh: bool = False


@asynccontextmanager
async def get_db() -> AsyncIterator:
    conn = await connect_db(_resolve_db_path())
    try:
        yield conn
    finally:
        await conn.close()


@router.post("/ai/analyze")
async def analyze_activity(body: AnalyzeRequest) -> dict[str, object]:
    async with get_db() as conn:
        activity = await get_activity(conn, body.activity_id)
        if activity is None:
            raise HTTPException(status_code=404, detail="Activity not found")

        if not body.force_refresh:
            cached = await get_ai_analysis(conn, body.activity_id)
            if cached:
                return {
                    "analysis": cached,
                    "cached": True,
                    "activity_id": body.activity_id,
                }

    return {
        "analysis": None,
        "cached": False,
        "stream_url": f"/api/ai/analyze/stream?activity_id={body.activity_id}",
    }


@router.get("/ai/analyze/stream")
async def analyze_stream(activity_id: str) -> StreamingResponse:
    return StreamingResponse(
        _analysis_stream(activity_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _analysis_stream(activity_id: str):
    async with get_db() as conn:
        activity = await get_activity(conn, activity_id)
        if not activity:
            yield f"data: {json.dumps({'error': 'Activity not found'}, ensure_ascii=False)}\n\n"
            return
        recent = await get_activities(conn, limit=10, offset=0)
        prompt = build_prompt(activity, recent)

    full_text: list[str] = []

    try:
        process = subprocess.Popen(
            [
                config.CLAUDE_CLI_PATH,
                "-p",
                prompt,
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        assert process.stdout is not None
        while True:
            line = await asyncio.to_thread(process.stdout.readline)
            if not line:
                if process.poll() is not None:
                    break
                await asyncio.sleep(0.05)
                continue

            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        chunk = block.get("text", "")
                        if not chunk:
                            continue
                        full_text.append(chunk)
                        yield f"data: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            elif event.get("type") == "result":
                analysis = "".join(full_text)
                if analysis:
                    async with get_db() as conn:
                        await save_ai_analysis(conn, activity_id, analysis)
                yield f"data: {json.dumps({'done': True, 'cached': False}, ensure_ascii=False)}\n\n"
                return

        await asyncio.to_thread(process.wait)
        analysis = "".join(full_text)
        if analysis:
            async with get_db() as conn:
                await save_ai_analysis(conn, activity_id, analysis)
        yield f"data: {json.dumps({'done': True, 'cached': False}, ensure_ascii=False)}\n\n"

    except FileNotFoundError:
        yield f"data: {json.dumps({'error': f'Claude CLI не найден: {config.CLAUDE_CLI_PATH}'}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"


def build_prompt(activity: dict, recent: list[dict]) -> str:
    def fmt_pace(seconds):
        if not seconds:
            return "—"
        return f"{seconds//60}:{seconds%60:02d}/км"

    def fmt_zones(item):
        total = sum(
            [
                item.get("hrm_fat_burning_duration") or 0,
                item.get("hrm_aerobic_duration") or 0,
                item.get("hrm_anaerobic_duration") or 0,
                item.get("hrm_extreme_duration") or 0,
            ]
        )
        if total == 0:
            return "нет данных"

        def pct(value):
            return f"{round((value or 0) / total * 100)}%"

        return (
            f"жиросжигание {pct(item.get('hrm_fat_burning_duration'))}, "
            f"аэробная {pct(item.get('hrm_aerobic_duration'))}, "
            f"анаэробная {pct(item.get('hrm_anaerobic_duration'))}, "
            f"экстремальная {pct(item.get('hrm_extreme_duration'))}"
        )

    recent_lines = "\n".join(
        [
            f"  {run['date'][:10]}: {run['distance_km']}км, "
            f"пульс {run['avg_hrm']}, темп {fmt_pace(run['avg_pace'])}, "
            f"нагрузка {run['train_load']}"
            for run in recent
        ]
    )

    return f"""Ты персональный тренер по бегу. Говори коротко и по-русски, как живой тренер — без воды. Пиши связным текстом, 3–5 предложений.

Бегун восстанавливается после травмы ступней и голеностопа. Цель: войти в ритм, бегать регулярно. Недавно купил новые кроссовки 361 KAIROS 2 (стек 34мм, перепад 8мм) — первые недели в них.

Пробежка {activity['date'][:10]}:
- Дистанция: {activity['distance_km']} км
- Пульс: {activity['avg_hrm']} уд/мин
- Темп: {fmt_pace(activity['avg_pace'])}
- Каденс: {activity['avg_cadence']} ш/мин
- Длина шага: {activity['avg_stride']} см
- Нагрузка: {activity['train_load']}
- Восстановление: {activity['recover_time']} ч
- Пульсовые зоны: {fmt_zones(activity)}

Последние 10 пробежек:
{recent_lines}

Дай короткий анализ этой пробежки и одну конкретную рекомендацию на следующую тренировку."""


def build_daily_prompt(activities: list[dict]) -> str:
    if not activities:
        return ""

    last = activities[0]
    last_date = datetime.fromisoformat(last["date"])
    now = datetime.now(timezone.utc)
    hours_since = round((now - last_date).total_seconds() / 3600)

    def fmt_pace(seconds):
        if not seconds:
            return "—"
        return f"{seconds//60}:{seconds%60:02d}/км"

    recent_lines = "\n".join(
        [
            f"  {run['date'][:10]}: {run['distance_km']}км, пульс {run['avg_hrm']}, "
            f"нагрузка {run['train_load']}, восстановление {run['recover_time']}ч"
            for run in activities[:7]
        ]
    )

    return f"""Ты персональный тренер по бегу. Отвечай строго в формате JSON.

Бегун восстанавливается после травмы ступней. Цель: войти в ритм, бегать регулярно.
Новые кроссовки 361 KAIROS 2 — первые недели в них.

Последняя пробежка: {last['date'][:10]}, {last['distance_km']}км,
пульс {last['avg_hrm']} уд/мин, темп {fmt_pace(last['avg_pace'])},
нагрузка {last['train_load']}, восстановление {last['recover_time']}ч.
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
- "run": всё в норме, можно бежать в обычном режиме"""


async def generate_daily_recommendation(sync_id: int | None = None) -> dict[str, str]:
    async with get_db() as conn:
        activities = await get_activities(conn, limit=10, offset=0)

    if not activities:
        return {"status": "run", "message": "Нет данных для анализа. Начни бегать!"}

    prompt = build_daily_prompt(activities)

    try:
        process = subprocess.Popen(
            [
                config.CLAUDE_CLI_PATH,
                "-p",
                prompt,
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        full_text: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        full_text.append(block["text"])

        process.wait()
        raw = "".join(full_text).strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        status = result.get("status", "run")
        message = result.get("message", "")

        async with get_db() as conn:
            await save_recommendation(conn, status, message, sync_id)

        return {"status": status, "message": message}
    except Exception as exc:
        return {"status": "run", "message": f"Не удалось получить анализ: {exc}"}


@router.get("/ai/recommendation")
async def get_recommendation() -> dict[str, object]:
    async with get_db() as conn:
        rec = await get_latest_recommendation(conn)
    if not rec:
        return {"status": None, "message": None, "generated_at": None}
    return rec
