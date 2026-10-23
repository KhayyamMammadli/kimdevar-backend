#!/usr/bin/env bash
set -euo pipefail
# Export settings from .env in your shell, or use the development command below.
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
