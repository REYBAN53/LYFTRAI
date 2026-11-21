#!/bin/sh
# Writes the runtime config consumed by index.html, so one image can point at any backend.
set -eu
target=/usr/share/nginx/html/env-config.js
escaped=$(printf '%s' "${API_BASE_URL:-http://localhost:8000}" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'window.__APP_CONFIG__ = { API_BASE_URL: "%s" };\n' "$escaped" > "$target"
echo "app-config: API_BASE_URL=${API_BASE_URL:-http://localhost:8000}"
