#!/usr/bin/env bash
set -euo pipefail

stop_docker=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stop-docker)
      stop_docker=true
      shift
      ;;
    *)
      echo "Usage: $0 [--stop-docker]" >&2
      exit 1
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$script_dir/.." && pwd)"
backend_compose="$root/backend/docker-compose.yml"
runtime_state_path="$root/.smartids-runtime.env"

backend_port="3100"
frontend_port="3000"
if [[ -f "$runtime_state_path" ]]; then
  # shellcheck disable=SC1090
  source "$runtime_state_path"
  backend_port="${SMARTIDS_BACKEND_PORT:-$backend_port}"
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to stop the IDS runtime on Linux." >&2
  exit 1
fi

sudo -v

echo "Stopping SmartIDS processes..."
pkill -f "backend/script.py start" || true
pkill -f "backend/script.py worker" || true
pkill -f "bun run dev -- --port $frontend_port" || true
sudo pkill -f "packet_capture.main" || true

# bun spawns a Next.js dev-server child whose argv doesn't contain the
# "bun run dev" pattern above, so it can survive the pkill; fall back to
# killing whatever is still bound to the known ports.
if command -v fuser >/dev/null 2>&1; then
  fuser -k "$frontend_port/tcp" >/dev/null 2>&1 || true
  fuser -k "$backend_port/tcp" >/dev/null 2>&1 || true
else
  echo "fuser not found; skipping port-based cleanup for stray frontend/backend processes." >&2
fi

if [[ "$stop_docker" == "true" ]]; then
  if [[ -f "$backend_compose" ]]; then
    echo "Stopping backend docker services..."
    sudo docker compose -f "$backend_compose" down
  else
    echo "Skipped docker stop: compose file missing at $backend_compose"
  fi
fi

rm -f "$runtime_state_path"

echo "SmartIDS stop sequence complete."
