#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

# Accept additional args for the 'up' step (e.g. --build)
UP_ARGS=("--detach")
if [ $# -gt 0 ]; then
  UP_ARGS+=("$@")
fi

docker compose down
exec docker compose up "${UP_ARGS[@]}"
