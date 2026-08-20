from __future__ import annotations

import asyncio
from collections import defaultdict
import json
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from portal.db import (
    connect_db,
    get_activities,
    get_activity,
    get_ai_analysis,
    get_health_states,
    get_latest_recommendation,
    get_settings,
    save_ai_analysis,
    save_recommendation,
)
from portal.infrastructure import config


router = APIRouter()


class AnalyzeRequest(BaseModel):
    activity_id: str
    force_refresh: bool = False


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _resolve_db_path() -> str:
    return str(Path(config.DB_PATH).expanduser())


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


async def build_activity_analysis_prompt(activity_id: str) -> str:
    async with get_db() as conn:
        activity = await get_activity(conn, activity_id)
        if not activity:
            raise HTTPException(status_code=404, detail="Activity not found")
        recent = await get_activities(conn, limit=10, offset=0)
        settings = await get_settings(conn)
        health_states = (await get_health_states(conn))[:3]
        return build_prompt(activity, recent, settings, health_states)


@router.get("/ai/analyze/prompt")
async def get_activity_analysis_prompt(activity_id: str) -> dict[str, object]:
    return {
        "activity_id": activity_id,
        "prompt": await build_activity_analysis_prompt(activity_id),
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
    try:
        prompt = await build_activity_analysis_prompt(activity_id)
    except HTTPException:
        yield f"data: {json.dumps({'error': 'Activity not found'}, ensure_ascii=False)}\n\n"
        return

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


def _render_template(template: str, values: dict[str, object]) -> str:
    normalized = {key: ("—" if value is None else str(value)) for key, value in values.items()}
    return template.format_map(_SafeDict(normalized))


def build_prompt(
    activity: dict,
    recent: list[dict],
    settings: dict[str, str],
    health_states: list[dict] | None = None,
    current_date: str | None = None,
) -> str:
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
    resolved_current_date = current_date or datetime.now(timezone.utc).date().isoformat()
    rendered_prompt = _render_template(
        settings["activity_prompt_template"],
        {
            "current_date": resolved_current_date,
            "activity_date": activity["date"][:10],
            "activity_distance_km": activity.get("distance_km"),
            "activity_avg_hrm": activity.get("avg_hrm"),
            "activity_avg_pace": fmt_pace(activity.get("avg_pace")),
            "activity_avg_cadence": activity.get("avg_cadence"),
            "activity_avg_stride": activity.get("avg_stride"),
            "activity_train_load": activity.get("train_load"),
            "activity_recover_time": activity.get("recover_time"),
            "activity_zones": fmt_zones(activity),
            "recent_lines": recent_lines,
            "health_lines": format_health_lines(health_states or []),
        },
    )
    if "{health_lines}" in settings["activity_prompt_template"]:
        return rendered_prompt

    health_lines = format_health_lines(health_states or [])
    if health_lines == "нет записей":
        return rendered_prompt
    return f"{rendered_prompt}\n\nТекущая дата: {resolved_current_date}\n\nПоследние записи о здоровье:\n{health_lines}"


def format_health_lines(health_states: list[dict]) -> str:
    if not health_states:
        return "нет записей"

    lines = []
    for index, state in enumerate(health_states[:3], start=1):
        started_at = str(state.get("started_at") or "—")
        ended_at = str(state.get("ended_at") or "сейчас")
        description = str(state.get("description") or "").strip()
        if not description:
            continue
        description_lines = "\n".join(
            f"    {line.strip()}" if line.strip() else ""
            for line in description.splitlines()
        )
        lines.append(
            f"{index}. Период: {started_at} — {ended_at}\n"
            f"   Описание:\n{description_lines}"
        )
    return "\n".join(lines) if lines else "нет записей"


def build_daily_prompt(
    activities: list[dict],
    settings: dict[str, str],
    health_states: list[dict] | None = None,
    last_activity_analysis: str | None = None,
    current_date: str | None = None,
) -> str:
    if not activities:
        return ""

    last = activities[0]
    last_date = datetime.fromisoformat(last["date"])
    now = datetime.now(timezone.utc)
    hours_since = round((now - last_date).total_seconds() / 3600)
    resolved_current_date = current_date or now.date().isoformat()

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
    return _render_template(
        settings["daily_prompt_template"],
        {
            "current_date": resolved_current_date,
            "last_date": last["date"][:10],
            "last_distance_km": last.get("distance_km"),
            "last_avg_hrm": last.get("avg_hrm"),
            "last_avg_pace": fmt_pace(last.get("avg_pace")),
            "last_train_load": last.get("train_load"),
            "last_recover_time": last.get("recover_time"),
            "hours_since": hours_since,
            "recent_lines": recent_lines,
            "health_lines": format_health_lines(health_states or []),
            "last_activity_analysis": last_activity_analysis or "нет сохранённого анализа",
        },
    )


def _parse_claude_json(raw: str) -> dict:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def _claude_error_message(event: dict) -> str | None:
    if not event.get("is_error") and not event.get("error"):
        return None

    result = event.get("result")
    if isinstance(result, str) and result.strip():
        return result.strip()

    message = event.get("message")
    if isinstance(message, dict):
        blocks = message.get("content") or []
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if text:
            return text

    return "Claude CLI returned an error"


def _recommendation_error_response(exc: Exception) -> dict[str, str]:
    raw_message = str(exc)
    if "Failed to authenticate" in raw_message or "OAuth session expired" in raw_message:
        return {
            "status": "error",
            "error_code": "claude_auth_expired",
            "message": "Авторизация Claude истекла. Чтобы обновить рекомендацию, войдите в Claude заново.",
            "action_label": "Войти в Claude",
            "action_url": "/claude-auth",
        }
    return {
        "status": "error",
        "error_code": "claude_unavailable",
        "message": "Не удалось обновить рекомендацию. Попробуйте позже или проверьте страницу Claude.",
        "action_label": "Открыть Claude",
        "action_url": "/claude-auth",
    }


def _monthly_goal_fallback(activities: list[dict], error: Exception | None = None) -> dict[str, object]:
    monthly: dict[str, dict[str, float | int]] = defaultdict(lambda: {"km": 0.0, "runs": 0})
    for activity in activities:
        try:
            dt = datetime.fromisoformat(str(activity.get("date", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        key = f"{dt.year}-{dt.month:02d}"
        monthly[key]["km"] = float(monthly[key]["km"]) + float(activity.get("distance_km") or 0)
        monthly[key]["runs"] = int(monthly[key]["runs"]) + 1

    if not monthly:
        km_goal = 40.0
        runs_goal = 10
    else:
        recent = [monthly[key] for key in sorted(monthly.keys())[-3:]]
        best_km = max(float(item["km"]) for item in recent)
        best_runs = max(int(item["runs"]) for item in recent)
        km_goal = round(max(20.0, min(best_km * 1.15, best_km + 10)), 1)
        runs_goal = max(6, min(31, round(best_runs * 1.15)))

    conservative_km = round(max(10.0, km_goal * 0.85), 1)
    conservative_runs = max(4, round(runs_goal * 0.85))
    ambitious_km = round(km_goal * 1.15, 1)
    ambitious_runs = min(31, max(runs_goal + 1, round(runs_goal * 1.15)))
    message = (
        f"Предлагаю цель {km_goal:.1f} км / {runs_goal} пробежек. "
        "Это умеренный шаг от недавнего объёма: достаточно для прогресса, но без резкого скачка нагрузки."
    )
    if error is not None:
        message = f"{message} AI-анализ сейчас недоступен, поэтому цель рассчитана по истории пробежек."

    return {
        "km_goal": km_goal,
        "runs_goal": runs_goal,
        "message": message,
        "conservative": {"km_goal": conservative_km, "runs_goal": conservative_runs},
        "ambitious": {"km_goal": ambitious_km, "runs_goal": ambitious_runs},
        "reasoning": "fallback" if error is None else "fallback_after_error",
    }


def _normalize_goal_suggestion(payload: dict, fallback: dict[str, object]) -> dict[str, object]:
    km_goal = round(float(payload.get("km_goal") or fallback["km_goal"]), 1)
    runs_goal = int(payload.get("runs_goal") or fallback["runs_goal"])
    km_goal = max(1.0, min(1000.0, km_goal))
    runs_goal = max(1, min(31, runs_goal))

    conservative_raw = payload.get("conservative") if isinstance(payload.get("conservative"), dict) else {}
    ambitious_raw = payload.get("ambitious") if isinstance(payload.get("ambitious"), dict) else {}
    fallback_conservative = fallback["conservative"]
    fallback_ambitious = fallback["ambitious"]

    return {
        "km_goal": km_goal,
        "runs_goal": runs_goal,
        "message": str(payload.get("message") or fallback["message"]),
        "conservative": {
            "km_goal": round(float(conservative_raw.get("km_goal") or fallback_conservative["km_goal"]), 1),
            "runs_goal": int(conservative_raw.get("runs_goal") or fallback_conservative["runs_goal"]),
        },
        "ambitious": {
            "km_goal": round(float(ambitious_raw.get("km_goal") or fallback_ambitious["km_goal"]), 1),
            "runs_goal": int(ambitious_raw.get("runs_goal") or fallback_ambitious["runs_goal"]),
        },
        "reasoning": str(payload.get("reasoning") or "ai"),
    }


async def generate_goal_suggestion(activities: list[dict], year: int, month: int) -> dict[str, object]:
    month_names = [
        "",
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    ]
    fallback = _monthly_goal_fallback(activities)
    if not activities:
        return fallback

    monthly: dict[str, dict[str, float | int]] = defaultdict(lambda: {"km": 0.0, "runs": 0})
    for activity in activities:
        try:
            dt = datetime.fromisoformat(str(activity.get("date", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        key = f"{dt.year}-{dt.month:02d}"
        monthly[key]["km"] = float(monthly[key]["km"]) + float(activity.get("distance_km") or 0)
        monthly[key]["runs"] = int(monthly[key]["runs"]) + 1

    monthly_lines = "\n".join(
        f"  {key}: {value['km']:.1f} км, {value['runs']} пробежек"
        for key, value in sorted(monthly.items())[-4:]
    )
    recent_lines = "\n".join(
        f"  {activity['date'][:10]}: {activity.get('distance_km')} км, "
        f"пульс {activity.get('avg_hrm')}, нагрузка {activity.get('train_load')}"
        for activity in activities[:10]
    )
    prompt = f"""Ты персональный тренер по бегу. Отвечай строго в формате JSON.

Бегун восстанавливается после травмы ступней и голеностопа. Цель: войти в ритм, бегать регулярно.
Нельзя увеличивать месячную нагрузку больше чем на 20% относительно лучшего предыдущего месяца.

Статистика по последним месяцам:
{monthly_lines}

Последние пробежки:
{recent_lines}

Предложи реалистичную цель на {month_names[month]} {year}.

Ответь ТОЛЬКО валидным JSON без markdown:
{{
  "km_goal": <число с одним знаком после запятой>,
  "runs_goal": <целое число>,
  "message": "2-3 предложения: почему именно эта цель и как её достичь",
  "conservative": {{"km_goal": <число>, "runs_goal": <число>}},
  "ambitious": {{"km_goal": <число>, "runs_goal": <число>}}
}}"""

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
        return _normalize_goal_suggestion(_parse_claude_json("".join(full_text)), fallback)
    except Exception as exc:
        return _monthly_goal_fallback(activities, error=exc)


async def generate_daily_recommendation(sync_id: int | None = None) -> dict[str, str]:
    async with get_db() as conn:
        activities = await get_activities(conn, limit=10, offset=0)
        settings = await get_settings(conn)
        health_states = (await get_health_states(conn))[:3]
        last_activity_analysis = None
        if activities:
            last_activity_analysis = await get_ai_analysis(conn, str(activities[0]["activity_id"]))

    if not activities:
        return {"status": "run", "message": "Нет данных для анализа. Начни бегать!"}

    prompt = build_daily_prompt(activities, settings, health_states, last_activity_analysis)

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
        claude_error: str | None = None
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_error = _claude_error_message(event)
            if event_error:
                claude_error = event_error
            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "text":
                        full_text.append(block["text"])

        return_code = process.wait()
        if claude_error:
            raise RuntimeError(claude_error)
        if return_code != 0:
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read().strip()
            raise RuntimeError(stderr or f"Claude CLI exited with code {return_code}")

        result = _parse_claude_json("".join(full_text))
        status = result.get("status", "run")
        message = result.get("message", "")

        async with get_db() as conn:
            await save_recommendation(conn, status, message, sync_id)

        return {"status": status, "message": message}
    except Exception as exc:
        return _recommendation_error_response(exc)


@router.get("/ai/recommendation/prompt")
async def get_daily_recommendation_prompt() -> dict[str, object]:
    async with get_db() as conn:
        activities = await get_activities(conn, limit=10, offset=0)
        settings = await get_settings(conn)
        health_states = (await get_health_states(conn))[:3]
        last_activity_analysis = None
        if activities:
            last_activity_analysis = await get_ai_analysis(conn, str(activities[0]["activity_id"]))
    return {"prompt": build_daily_prompt(activities, settings, health_states, last_activity_analysis)}


@router.get("/ai/recommendation")
async def get_recommendation() -> dict[str, object]:
    async with get_db() as conn:
        rec = await get_latest_recommendation(conn)
    if not rec:
        return {"status": None, "message": None, "generated_at": None}
    return rec
