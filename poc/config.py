"""Runtime settings, read from environment variables or a .env file in the project root."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:  # python-dotenv is optional; plain environment variables also work
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "90"))

PORT = int(os.getenv("PORT", "8000"))

# A finding below this confidence is never priced; it becomes an inspector flag.
MIN_CONFIDENCE = 0.6

DATA_DIR = ROOT / "poc" / "data"
SAMPLES_DIR = DATA_DIR / "samples"
STATIC_DIR = ROOT / "static"


def openai_enabled() -> bool:
    key = OPENAI_API_KEY
    return bool(key) and not key.startswith("sk-your")
