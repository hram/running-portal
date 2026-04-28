# Running Portal

FastAPI-based local portal for browsing running activities and syncing data from Mi Fitness.

## Setup

```bash
pip install -e ".[dev]"
cp .env.example .env
```

## Run

```bash
uvicorn portal.main:app --reload --port 8001
```

## Mi Fitness auth

The portal stores Mi Fitness auth state in `MI_FITNESS_STATE_PATH`.
When Mi Fitness returns `401`, sync first tries to refresh the saved state and validates it with a lightweight activity request.

For unattended sync, set `MI_FITNESS_PASSWORD` in `.env`; the portal will silently re-login with the saved email, or `MI_FITNESS_EMAIL` if set. Without the password, a rejected session requires logging in again through the UI.

## Test

```bash
python -m pytest tests/ -v
```
