#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export MONGODB_URI="${MONGODB_URI:-mongodb://127.0.0.1:27017}"
export MONGODB_DATABASE="${MONGODB_DATABASE:-crop_forensics}"
demo_port="${PORT:-8000}"
if curl --silent --fail --max-time 2 "http://127.0.0.1:${demo_port}/api/health" >/dev/null 2>&1; then
  echo "FieldTrace is already running at http://127.0.0.1:${demo_port}"
  exit 0
fi
exec .venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port "${demo_port}"
