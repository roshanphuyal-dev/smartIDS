#!/usr/bin/env bash
set -euo pipefail

base_url="http://127.0.0.1:3100"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url|-b)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --base-url" >&2
        exit 1
      fi
      base_url="$2"
      shift 2
      ;;
    *)
      echo "Usage: $0 [--base-url http://127.0.0.1:3100]" >&2
      exit 1
      ;;
  esac
done

base_url="${base_url%/}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$script_dir/.." && pwd)"
backend_dir="$root/backend"
frontend_dir="$root/frontend"
backend_compose="$backend_dir/docker-compose.yml"
venv_python="$root/.venv/bin/python"
runtime_state_path="$root/.smartids-runtime.env"
backend_port="${base_url##*:}"

if [[ ! -d "$backend_dir" ]]; then
  echo "Backend directory not found: $backend_dir" >&2
  exit 1
fi
if [[ ! -d "$frontend_dir" ]]; then
  echo "Frontend directory not found: $frontend_dir" >&2
  exit 1
fi
if [[ ! -f "$backend_compose" ]]; then
  echo "Backend docker-compose file not found: $backend_compose" >&2
  exit 1
fi

if [[ -x "$venv_python" ]]; then
  python_exe="$venv_python"
else
  python_exe="python3"
fi

cd "$root"

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to start the IDS runtime on Linux." >&2
  exit 1
fi

sudo -v

echo "[1/6] Starting local infra (backend/docker-compose.yml)..."
sudo docker compose -f "$backend_compose" up -d

echo "[2/6] Applying backend migrations..."
"$python_exe" "$backend_dir/script.py" migrate upgrade

echo "[3/6] Starting backend API in background..."
nohup "$python_exe" "$backend_dir/script.py" start --port "$backend_port" >"$root/.smartids-backend.log" 2>&1 &

echo "[4/6] Starting backend worker in background..."
nohup "$python_exe" "$backend_dir/script.py" worker >"$root/.smartids-worker.log" 2>&1 &

echo "[5/6] Starting frontend dev server in background..."
(
  cd "$frontend_dir"
  nohup env \
    NEXT_PUBLIC_IDS_REST_BASE_URL="$base_url/api/v1" \
    IDS_REST_BASE_URL="$base_url/api/v1" \
    NEXT_PUBLIC_IDS_WS_URL="ws://127.0.0.1:$backend_port/api/v1/realtime/ws" \
    bun run dev -- --port 3000 >"$root/.smartids-frontend.log" 2>&1 &
)

echo "[6/6] Starting IDS runtime (packet capture + ML) with sudo..."
sudo nohup env \
  SMARTIDS_IDS_EVENT_ENDPOINT="$base_url/api/v1/ids-events" \
  SMARTIDS_SESSION_UPDATE_ENDPOINT="$base_url/api/v1/sessions/upsert" \
  SMARTIDS_BLOCK_EVENT_ENDPOINT="$base_url/api/v1/block-events/upsert" \
  SMARTIDS_ENGINE_TELEMETRY_ENDPOINT="$base_url/api/v1/engine-telemetry" \
  SMARTIDS_COMMANDS_ENDPOINT="$base_url/api/v1/engine-commands" \
  SMARTIDS_COMMANDS_ACK_ENDPOINT="$base_url/api/v1/engine-commands/ack" \
  "$python_exe" -m packet_capture.main >"$root/.smartids-ids-runtime.log" 2>&1 &

cat >"$runtime_state_path" <<EOF
SMARTIDS_BACKEND_BASE_URL=$base_url
SMARTIDS_BACKEND_PORT=$backend_port
NEXT_PUBLIC_IDS_REST_BASE_URL=$base_url/api/v1
IDS_REST_BASE_URL=$base_url/api/v1
NEXT_PUBLIC_IDS_WS_URL=ws://127.0.0.1:$backend_port/api/v1/realtime/ws
EOF

echo "Started SmartIDS services."
echo "- Backend API:    $base_url"
echo "- Frontend:       http://127.0.0.1:3000"
echo "- IDS runtime:    packet_capture.main"
echo "- Runtime file:   .smartids-runtime.env"
