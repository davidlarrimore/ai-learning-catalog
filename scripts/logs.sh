#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

if [ $# -eq 0 ]; then
  set -- logs --follow
else
  set -- logs "$@"
fi

exec docker compose "$@"
