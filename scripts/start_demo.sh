#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export MONGODB_URI="${MONGODB_URI:-mongodb://127.0.0.1:27017}"
export MONGODB_DATABASE="${MONGODB_DATABASE:-crop_forensics}"
exec .venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port "${PORT:-8000}"
