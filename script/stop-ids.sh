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

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to stop the IDS runtime on Linux." >&2
  exit 1
fi

sudo -v

echo "Stopping SmartIDS processes..."
pkill -f "backend/script.py start" || true
pkill -f "backend/script.py worker" || true
pkill -f "bun run dev -- --port 3000" || true
sudo pkill -f "packet_capture.main" || true

if [[ "$stop_docker" == "true" ]]; then
  if [[ -f "$backend_compose" ]]; then
    echo "Stopping backend docker services..."
    sudo docker compose -f "$backend_compose" down
  else
    echo "Skipped docker stop: compose file missing at $backend_compose"
  fi
fi

echo "SmartIDS stop sequence complete."
