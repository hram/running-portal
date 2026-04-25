from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

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
        session = await asyncio.to_thread(
            client.login_with_password,
            email=request.email,
            password=request.password,
            device_id=client.generate_device_id(),
        )
        save_state(session.to_auth_state(), _resolve_state_path())
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/auth/status")
async def auth_status() -> dict[str, object]:
    _ = get_auth_client()
    state = load_state(_resolve_state_path())
    return {
        "authenticated": state is not None,
        "email": None if state is None else state.email,
        "expires_at": None if state is None else state.updated_at,
    }
