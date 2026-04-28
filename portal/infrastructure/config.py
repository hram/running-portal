from __future__ import annotations

import os


CLAUDE_CLI_PATH = os.getenv("CLAUDE_CLI_PATH", "/home/hram/.local/bin/claude")
DB_PATH = os.getenv("DB_PATH", "~/.running_portal/portal.db")
MI_FITNESS_STATE_PATH = os.getenv("MI_FITNESS_STATE_PATH", "~/.running_portal/auth.json")
MI_FITNESS_CACHE_DIR = os.getenv("MI_FITNESS_CACHE_DIR", "~/.running_portal/fds_cache")
MI_FITNESS_COUNTRY_CODE = os.getenv("MI_FITNESS_COUNTRY_CODE", "RU")
MI_FITNESS_EMAIL = os.getenv("MI_FITNESS_EMAIL")
MI_FITNESS_PASSWORD = os.getenv("MI_FITNESS_PASSWORD")
