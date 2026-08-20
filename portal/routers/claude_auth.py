from __future__ import annotations

import asyncio
import json
import os
import re
import select
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from portal.infrastructure import config


router = APIRouter()


class ClaudeAuthUpdateRequest(BaseModel):
    claudeAiOauth: str


class ClaudeAuthCodeRequest(BaseModel):
    session_id: str
    code: str


@dataclass
class ClaudeLoginSession:
    session_id: str
    process: subprocess.Popen
    login_url: str
    output: str


_LOGIN_URL_PATTERN = re.compile(r"https://\S+")
_login_session: ClaudeLoginSession | None = None


def _credentials_path() -> Path:
    return Path.home() / ".claude" / ".credentials.json"


def _write_credentials(token: str) -> Path:
    cleaned = token.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="claudeAiOauth must not be blank")

    path = _credentials_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)

    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps({"claudeAiOauth": cleaned}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(temp_path, 0o600)
    temp_path.replace(path)
    os.chmod(path, 0o600)
    return path


def _read_login_output_until_url(process: subprocess.Popen, timeout_seconds: float = 10.0) -> tuple[str, str | None]:
    if process.stdout is None:
        return "", None

    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    fd = process.stdout.fileno()

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        readable, _, _ = select.select([fd], [], [], min(0.25, remaining))
        if not readable:
            if process.poll() is not None:
                break
            continue

        chunk = os.read(fd, 4096)
        if not chunk:
            break
        output.extend(chunk)

        decoded = output.decode("utf-8", errors="replace")
        match = _LOGIN_URL_PATTERN.search(decoded)
        if match:
            return decoded, match.group(0)

    return output.decode("utf-8", errors="replace"), None


def _cleanup_login_session() -> None:
    global _login_session
    if _login_session and _login_session.process.poll() is None:
        _login_session.process.terminate()
    _login_session = None


def _start_login_session() -> dict[str, object]:
    global _login_session
    if _login_session and _login_session.process.poll() is None:
        return {
            "session_id": _login_session.session_id,
            "login_url": _login_session.login_url,
        }

    process = subprocess.Popen(
        [config.CLAUDE_CLI_PATH, "auth", "login"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
    )
    output, login_url = _read_login_output_until_url(process)
    if not login_url:
        if process.poll() is None:
            process.terminate()
        raise HTTPException(status_code=502, detail="Claude login URL was not found in CLI output")

    _login_session = ClaudeLoginSession(
        session_id=str(uuid.uuid4()),
        process=process,
        login_url=login_url,
        output=output,
    )
    return {
        "session_id": _login_session.session_id,
        "login_url": login_url,
    }


def _submit_login_code(session_id: str, code: str) -> dict[str, object]:
    global _login_session
    cleaned = code.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="code must not be blank")
    if not _login_session or _login_session.session_id != session_id:
        raise HTTPException(status_code=404, detail="Claude login session not found")
    if _login_session.process.poll() is not None:
        _login_session = None
        raise HTTPException(status_code=410, detail="Claude login session has already finished")
    if _login_session.process.stdin is None:
        _cleanup_login_session()
        raise HTTPException(status_code=500, detail="Claude login session stdin is unavailable")

    process = _login_session.process
    try:
        process.stdin.write((cleaned + "\n").encode("utf-8"))
        process.stdin.flush()
        stdout, _ = process.communicate(timeout=45)
    except subprocess.TimeoutExpired as exc:
        _cleanup_login_session()
        raise HTTPException(status_code=504, detail="Claude login did not finish after code submission") from exc

    output = _login_session.output + (stdout or b"").decode("utf-8", errors="replace")
    return_code = process.returncode
    _login_session = None

    if return_code != 0:
        tail = output.strip().splitlines()[-1] if output.strip() else "Claude login failed"
        raise HTTPException(status_code=502, detail=tail)

    return {
        "ok": True,
        "credentials_path": str(_credentials_path()),
    }


@router.get("/claude-auth")
async def get_claude_auth_status() -> dict[str, object]:
    path = _credentials_path()
    return {
        "credentials_path": str(path),
        "configured": path.exists(),
    }


@router.post("/claude-auth")
async def update_claude_auth(body: ClaudeAuthUpdateRequest) -> dict[str, object]:
    path = _write_credentials(body.claudeAiOauth)
    from portal.routers.ai import clear_recommendation_error

    await clear_recommendation_error()
    return {
        "ok": True,
        "credentials_path": str(path),
    }


@router.post("/claude-auth/login-url")
async def create_claude_login_url() -> dict[str, object]:
    return await asyncio.to_thread(_start_login_session)


@router.post("/claude-auth/login-code")
async def submit_claude_login_code(body: ClaudeAuthCodeRequest) -> dict[str, object]:
    result = await asyncio.to_thread(_submit_login_code, body.session_id, body.code)
    from portal.routers.ai import clear_recommendation_error

    await clear_recommendation_error()
    return result
