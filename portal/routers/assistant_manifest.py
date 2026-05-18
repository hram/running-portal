from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(tags=["assistant"])


ASSISTANT_INTEGRATION_MANIFEST = {
    "name": "running_portal",
    "title": "Running Portal",
    "version": "1.0",
    "description": "Беговые цели, прогресс и темп выполнения.",
    "capabilities": [
        {
            "id": "monthly_running_goal",
            "type": "context",
            "title": "Статус беговой цели",
            "description": "Возвращает месячную беговую цель, прогресс и нужный темп.",
            "endpoint": {
                "method": "GET",
                "path": "/api/goals/monthly",
            },
            "prompt": {
                "section": "Бег",
                "summary_template": (
                    "[Бег] Цель: {goal.runs_goal} пробежек / {goal.km_goal} км\n"
                    "  Выполнено: {progress.runs_count} пробежек / {progress.total_km:.1f} км\n"
                    "  Осталось: {runs_remaining} пробежек за {days_remaining} дней\n"
                    "  Нужный темп: {needed_km_per_day} км/день\n"
                    "  Статус: {status}"
                ),
            },
            "relevance": {
                "status_path": "status",
                "default_score": 0.2,
                "status_scores": {
                    "behind": 0.7,
                    "slightly_behind": 0.5,
                    "on_track": 0.3,
                },
                "keywords": ["бег", "пробеж", "км", "километр", "run"],
            },
        },
        {
            "id": "daily_running_recommendation",
            "type": "context",
            "title": "Ответ на сегодня",
            "description": "Возвращает актуальную рекомендацию: можно ли сегодня бежать.",
            "endpoint": {
                "method": "GET",
                "path": "/api/ai/recommendation",
            },
            "prompt": {
                "section": "Бег сегодня",
                "summary_template": (
                    "[Бег сегодня] Статус: {status}\n"
                    "  Рекомендация: {message}\n"
                    "  Обновлено: {generated_at}"
                ),
            },
            "relevance": {
                "status_path": "status",
                "default_score": 0.2,
                "status_scores": {
                    "rest": 0.7,
                    "run_easy": 0.5,
                    "run": 0.4,
                },
                "keywords": ["бежать", "можно", "сегодня", "завтра", "тренировка"],
            },
        }
    ],
}


@router.get("/.well-known/assistant-integration.json")
async def assistant_integration_manifest() -> dict:
    return ASSISTANT_INTEGRATION_MANIFEST
