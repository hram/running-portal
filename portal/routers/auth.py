from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from mi_fitness_sync.exceptions import CaptchaRequiredError, NotificationRequiredError, Step2RequiredError
from mi_fitness_sync.auth.store import load_state, save_state

from portal.sync import _resolve_state_path, get_auth_client


router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
async def login(request: LoginRequest) -> dict[str, object]:
    client = get_auth_client()
    try:
        existing_state = load_state(_resolve_state_path())
        device_id = existing_state.device_id if existing_state is not None else client.generate_device_id()
        session = await asyncio.to_thread(
            client.login_with_password,
            email=request.email,
            password=request.password,
            device_id=device_id,
        )
        save_state(session.to_auth_state(), _resolve_state_path())
        return {"success": True}
    except Exception as exc:
        return {"success": False, **format_auth_error(exc)}


@router.get("/auth/status")
async def auth_status() -> dict[str, object]:
    _ = get_auth_client()
    state = load_state(_resolve_state_path())
    return {
        "authenticated": state is not None,
        "email": None if state is None else state.email,
        "expires_at": None if state is None else state.updated_at,
    }


def format_auth_error(exc: Exception) -> dict[str, object]:
    if isinstance(exc, CaptchaRequiredError):
        return {
            "error": str(exc),
            "action": "captcha",
            "verification_url": exc.captcha_url,
        }
    if isinstance(exc, NotificationRequiredError):
        return {
            "error": str(exc),
            "action": "verification",
            "verification_url": exc.notification_url,
        }
    if isinstance(exc, Step2RequiredError):
        payload = exc.payload or {}
        notification_url = payload.get("notificationUrl")
        if isinstance(notification_url, str) and notification_url:
            if notification_url.startswith("/"):
                notification_url = f"https://account.xiaomi.com{notification_url}"
            return {
                "error": str(exc),
                "action": "verification",
                "verification_url": notification_url,
            }

        details: dict[str, object] = {}
        for key in ("step1Token", "code", "desc", "description", "info"):
            value = payload.get(key)
            if value:
                details[key] = value
        if all(isinstance(payload.get(key), str) and payload.get(key) for key in ("_sign", "qs", "callback")):
            details["meta_login_data_present"] = True
        return {
            "error": str(exc),
            "action": "step2",
            "details": details,
        }
    return {"error": str(exc)}
