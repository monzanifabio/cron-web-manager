#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")

cd "$REPO_DIR/frontend"
npm run build

cd "$REPO_DIR/backend"

if [ -x "$REPO_DIR/backend/venv/bin/uvicorn" ]; then
	exec "$REPO_DIR/backend/venv/bin/uvicorn" main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
fi

if command -v uvicorn >/dev/null 2>&1; then
	exec uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
fi

echo "uvicorn not found. Install backend dependencies or create backend/venv first." >&2
exit 1