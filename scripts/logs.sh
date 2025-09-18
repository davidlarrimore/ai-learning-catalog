#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT_DIR"

if [ -z "${APP_LOG_LEVEL:-}" ] && [ -f .env ]; then
  while IFS= read -r line; do
    case "$line" in
      APP_LOG_LEVEL=*)
        value=${line#APP_LOG_LEVEL=}
        value=${value%%#*}
        value=$(printf '%s' "$value" | tr -d ' "')
        value=${value//\'/}
        if [ -n "$value" ]; then
          APP_LOG_LEVEL=$value
        fi
        ;;
    esac
  done < .env
fi

APP_LOG_LEVEL=${APP_LOG_LEVEL:-INFO}
printf 'Streaming logs (APP_LOG_LEVEL=%s)\n' "$APP_LOG_LEVEL"

if [ $# -eq 0 ]; then
  set -- logs --follow
else
  set -- logs "$@"
fi

exec docker compose "$@"
