#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(dirname "$SCRIPT_DIR")

cd "$REPO_DIR/frontend"
npm run build

exec sh "$REPO_DIR/scripts/start-built.sh"
