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

## Test

```bash
pytest tests/ -v
```
