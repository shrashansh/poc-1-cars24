#!/usr/bin/env bash
# macOS / Linux: ./run.sh
set -e
cd "$(dirname "$0")"
[ -f .env ] || { cp .env.example .env; echo "Created .env - paste your OPENAI_API_KEY into it, then run ./run.sh again."; exit 1; }
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
if command -v uv >/dev/null 2>&1; then
  uv pip install -q -r requirements.txt   # uv-created venvs ship without pip
else
  python -m pip install -q -r requirements.txt
fi
python run.py
