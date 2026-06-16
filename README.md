# SmartIDS

SmartIDS is a passive, userland intrusion detection system with a FastAPI backend, Next.js dashboard, live packet/session analysis, ML-assisted detection, and automated reactive mitigation.

SmartIDS is not a kernel-level inline IPS. Packet capture is performed with Scapy from userland, so the engine observes packet copies after the OS networking stack has already received them. Response actions can block or watchlist future traffic, but they do not guarantee prevention of the packet that triggered the detection.

## What SmartIDS Does

- Captures network packets through a passive IDS runtime.
- Builds active network sessions from parsed packet metadata.
- Extracts live-compatible ML features from sessions.
- Runs heuristic and ML detection outside the packet sniff callback.
- Reports IDS events, session updates, block events, telemetry, and engine-command acknowledgements to the backend.
- Stores and queries alerts, sessions, threats, blocked IPs, and engine commands through the backend.
- Broadcasts realtime dashboard updates over WebSocket channels.
- Can reactively block, unblock, watchlist, or unwatchlist IPs through platform firewall adapters.

## How It Works

```text
Scapy packet copy
  -> packet_capture parser
  -> bounded queue
  -> PacketProcessor
  -> traffic_engine session builder
  -> feature_engine runtime feature extractor
  -> heuristic + ML detection
  -> response_engine policy/blocker
  -> FastAPI backend ingest endpoints
  -> PostgreSQL + realtime WebSocket dashboard
```

The sniff callback is intentionally tiny: parse packet data, update lightweight counters, enqueue, and return. ML inference, session aggregation, backend HTTP calls, database writes, file I/O, and blocking response actions run outside the sniff callback.

## Repository Layout

- `packet_capture/` - Scapy sniffer, packet parsing, processor orchestration, backend forwarders, engine telemetry.
- `traffic_engine/` - Session keys, session model, active-session builder, expiration and prediction triggers.
- `feature_engine/` - Runtime feature extraction and safe statistics helpers.
- `ml/` - Canonical feature schema, CICIDS2017 mapping/validation, training, evaluation, runtime model loading.
- `response_engine/` - Firewall adapters, response policy, block/watchlist state, durable processed-command dedupe.
- `backend/` - FastAPI API, auth, persistence, realtime WebSocket channels, migrations, smoke checks.
- `database/` - Canonical shared database notes and backend DB barrel.
- `frontend/` - Next.js/Bun dashboard.
- `script/` - Windows helper scripts for starting, stopping, checking, and smoke-feeding SmartIDS.
- `tests/` - Unit and integration tests for backend, ML, packet runtime, and contracts.
- `docs/` - Architecture context, plans, lab validation notes, and roadmap material.

## Requirements

### Shared

- Git
- Python 3.12 recommended
- Docker Desktop or Docker Engine with Compose
- PostgreSQL and Redis are started by `backend/docker-compose.yml`
- Bun for the frontend

### Windows

- PowerShell 7 or Windows PowerShell
- Npcap installed with packet capture support
- Run the IDS runtime terminal as Administrator when sniffing live traffic
- Python venv path used by project scripts: `.venv_windows`

### Linux

- `python3-venv`, build tools, and libpcap headers
- Root/sudo capability for live packet capture and firewall response actions
- Run validation in an isolated lab VM when testing blocking behavior

Example Linux package install:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev build-essential libpcap-dev docker.io docker-compose-plugin
```

Install Bun on Linux/macOS:

```bash
curl -fsSL https://bun.sh/install | bash
```

## Environment Files

SmartIDS uses two main env files:

- `backend/.env` - backend API, database, Redis, auth, CORS, email, and backend-side service token.
- `.env` - IDS runtime forwarding endpoints and runtime-only knobs.

Create them from examples:

### Windows

```powershell
Copy-Item .\backend\.env.example .\backend\.env
Copy-Item .\database\.env.example .\database\.env
if (-not (Test-Path .\.env)) { New-Item -ItemType File .\.env | Out-Null }
```

### Linux

```bash
cp backend/.env.example backend/.env
cp database/.env.example database/.env
touch .env
```

Important service-token rule:

- Backend ingest endpoints use `INTERNAL_SERVICE_TOKEN` from `backend/.env`.
- IDS runtime forwarders use `SMARTIDS_INTERNAL_SERVICE_TOKEN` from root `.env`.
- Set both to the same long random value when service-to-service auth is enabled.

Minimum local root `.env` for IDS runtime forwarding:

```env
SMARTIDS_IDS_EVENT_ENDPOINT=http://127.0.0.1:3000/api/v1/ids-events
SMARTIDS_SESSION_UPDATE_ENDPOINT=http://127.0.0.1:3000/api/v1/sessions/upsert
SMARTIDS_BLOCK_EVENT_ENDPOINT=http://127.0.0.1:3000/api/v1/block-events/upsert
SMARTIDS_ENGINE_TELEMETRY_ENDPOINT=http://127.0.0.1:3000/api/v1/engine-telemetry
SMARTIDS_COMMANDS_ENDPOINT=http://127.0.0.1:3000/api/v1/engine-commands
SMARTIDS_COMMANDS_ACK_ENDPOINT=http://127.0.0.1:3000/api/v1/engine-commands/ack
SMARTIDS_COMMANDS_POLL_INTERVAL_SECONDS=1.5
SMARTIDS_ENGINE_TELEMETRY_INTERVAL_SECONDS=30
SMARTIDS_INTERNAL_SERVICE_TOKEN=replace-with-the-same-value-as-backend-internal-token
SMARTIDS_IP_ACTIVITY_MAX_TRACKED_IPS=10000
SMARTIDS_IP_ACTIVITY_MAX_ACTION_HISTORY=25
SMARTIDS_IP_ACTIVITY_MAX_FILE_ENTRIES=50000
SMARTIDS_IP_ACTIVITY_FILE_COMPACTION_INTERVAL_RECORDS=100
SMARTIDS_PROCESSED_COMMAND_MAX_IDS=10000
```

## Install Dependencies

### Windows

```powershell
py -3.12 -m venv .venv_windows
.\.venv_windows\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\config\requirements_windows.txt
pip install -r .\backend\requirements.txt

Set-Location .\frontend
bun install
Set-Location ..
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r config/requirements.txt
pip install -r backend/requirements.txt

cd frontend
bun install
cd ..
```

## Start Infrastructure

### Windows

```powershell
docker compose -f .\backend\docker-compose.yml up -d
```

### Linux

```bash
docker compose -f backend/docker-compose.yml up -d
```

PostgreSQL is exposed on `localhost:8080`; Redis is exposed on `localhost:6379`.

## Apply Backend Migrations

### Windows

```powershell
.\.venv_windows\Scripts\python.exe .\backend\script.py migrate upgrade
```

### Linux

```bash
.venv/bin/python backend/script.py migrate upgrade
```

## Start SmartIDS Manually

Use separate terminals for backend API, worker, frontend, and IDS runtime.

### 1. Backend API

Windows:

```powershell
.\.venv_windows\Scripts\python.exe .\backend\script.py start --port 3000
```

Linux:

```bash
.venv/bin/python backend/script.py start --host 127.0.0.1 --port 3000
```

Backend URL: `http://127.0.0.1:3000`

### 2. Backend Worker

Windows:

```powershell
.\.venv_windows\Scripts\python.exe .\backend\script.py worker
```

Linux:

```bash
.venv/bin/python backend/script.py worker
```

### 3. Frontend Dashboard

Windows and Linux:

```bash
cd frontend
bun run dev -- --port 3001
```

Open `http://127.0.0.1:3001`.

If you want the frontend to point at a non-default backend, set:

```bash
NEXT_PUBLIC_IDS_REST_BASE_URL=http://127.0.0.1:3000/api/v1
IDS_REST_BASE_URL=http://127.0.0.1:3000/api/v1
NEXT_PUBLIC_IDS_WS_URL=ws://127.0.0.1:3000/api/v1/realtime/ws
```

### 4. IDS Runtime

Windows, in an Administrator PowerShell:

```powershell
.\.venv_windows\Scripts\python.exe -m packet_capture.main
```

Linux:

```bash
sudo .venv/bin/python -m packet_capture.main
```

The IDS runtime is passive capture plus reactive mitigation. Test live capture/blocking only on networks and hosts you own or have explicit permission to monitor.

## Windows One-Command Helper

The PowerShell helpers start or stop the local stack for development.

Start:

```powershell
.\script\start-smartids.ps1 -BaseUrl http://127.0.0.1:3000
```

Start with hidden helper windows:

```powershell
.\script\start-smartids.ps1 -BaseUrl http://127.0.0.1:3000 -HideWindows
```

Status:

```powershell
.\script\status-smartids.ps1
```

Feed smoke payloads into a running backend:

```powershell
.\script\feed-smartids-testdata.ps1 -BaseUrl http://127.0.0.1:3000
```

Stop app processes:

```powershell
.\script\stop-smartids.ps1
```

Stop app processes and Docker infra:

```powershell
.\script\stop-smartids.ps1 -StopDocker
```

## Backend Smoke Checks

Run after backend API is up.

Windows:

```powershell
.\.venv_windows\Scripts\python.exe .\backend\smoke\api_smoke_unified_reporting.py --base-url http://127.0.0.1:3000
.\.venv_windows\Scripts\python.exe .\backend\smoke\api_smoke_engine_commands.py --base-url http://127.0.0.1:3000
.\.venv_windows\Scripts\python.exe .\backend\smoke\api_smoke_engine_telemetry.py --base-url http://127.0.0.1:3000
.\.venv_windows\Scripts\python.exe .\backend\smoke\api_smoke_sessions.py --base-url http://127.0.0.1:3000
.\.venv_windows\Scripts\python.exe .\backend\smoke\api_smoke_response_actions.py --base-url http://127.0.0.1:3000
```

Linux:

```bash
.venv/bin/python backend/smoke/api_smoke_unified_reporting.py --base-url http://127.0.0.1:3000
.venv/bin/python backend/smoke/api_smoke_engine_commands.py --base-url http://127.0.0.1:3000
.venv/bin/python backend/smoke/api_smoke_engine_telemetry.py --base-url http://127.0.0.1:3000
.venv/bin/python backend/smoke/api_smoke_sessions.py --base-url http://127.0.0.1:3000
.venv/bin/python backend/smoke/api_smoke_response_actions.py --base-url http://127.0.0.1:3000
```

Service-level checks that do not require HTTP:

Windows:

```powershell
.\.venv_windows\Scripts\python.exe .\backend\smoke\smoke_database_barrel_import.py
.\.venv_windows\Scripts\python.exe .\backend\smoke\smoke_session_finalization_reasons.py
```

Linux:

```bash
.venv/bin/python backend/smoke/smoke_database_barrel_import.py
.venv/bin/python backend/smoke/smoke_session_finalization_reasons.py
```

## Run Tests

Windows:

```powershell
.\.venv_windows\Scripts\python.exe -m unittest discover tests
```

Linux:

```bash
.venv/bin/python -m unittest discover tests
```

Focused examples:

```bash
python -m unittest tests.unit.core.test_engine_telemetry
python -m unittest tests.unit.core.test_ip_activity_tracker
python -m unittest tests.unit.core.test_engine_command_dedupe
python -m unittest tests.integration.api.test_internal_service_auth
```

## ML Dataset And Model Workflow

The runtime ML contract is strict: training, evaluation, saved artifacts, and live prediction must use exactly `ml/features/schema.py::FEATURE_COLUMNS`.

Prepare CICIDS2017 data from a verified raw CSV or directory of raw CSVs:

Windows:

```powershell
.\.venv_windows\Scripts\python.exe -m ml.datasets.prepare_cicids2017 `
  --source C:\path\to\raw-cicids2017 `
  --output-dir ml\data
```

Linux:

```bash
.venv/bin/python -m ml.datasets.prepare_cicids2017 \
  --source /path/to/raw-cicids2017 \
  --output-dir ml/data
```

Build, evaluate, verify, and atomically activate a live-compatible model:

Windows:

```powershell
.\.venv_windows\Scripts\python.exe -m ml.training.build_cicids2017_model
```

Linux:

```bash
.venv/bin/python -m ml.training.build_cicids2017_model
```

If activation fails, existing active artifacts under `ml/saved_models` are preserved. Stop the IDS runtime before activation on Windows so open model files do not block directory replacement.

Contract examples live in:

- `ml/contracts/cicids2017_training_row.example.json`
- `ml/contracts/live_prediction_input.example.json`
- `ml/contracts/live_prediction_output.example.json`

## Engine Command Contract

The backend can queue commands for the IDS runtime:

- `POST /api/v1/engine-commands`
- `GET /api/v1/engine-commands?limit=20`
- `POST /api/v1/engine-commands/ack`

Supported actions:

- `block`
- `unblock`
- `watchlist`
- `unwatchlist`

The runtime polls commands from `SMARTIDS_COMMANDS_ENDPOINT`, applies them through `response_engine`, acknowledges via `SMARTIDS_COMMANDS_ACK_ENDPOINT`, and persists processed command IDs in `logs/processed_engine_commands.json` to avoid re-applying the same command after restart.

## Engine Telemetry

When `SMARTIDS_ENGINE_TELEMETRY_ENDPOINT` is configured, the IDS runtime forwards:

- total packets received
- packets received per 30 seconds
- processed packets
- dropped/lost packet counters
- packet queue size, max size, and usage percentage
- active sessions
- ML prediction count, 30-second rate, and last prediction latency
- active network endpoint exchanges
- packet-loss heads-up flags instead of runtime errors

Process/application attribution is not available in the passive packet path yet; the runtime reports endpoint exchanges by IP/port/protocol.

## Logs And Runtime State

- `logs/ip_activity.jsonl` - bounded IP activity records.
- `logs/processed_engine_commands.json` - bounded processed command ID dedupe store.
- `.smartids-runtime.env` - generated by Windows helper scripts with current local URLs.
- Backend data is stored in PostgreSQL through the canonical backend/database setup.

## Safe Validation

Use `docs/LINUX_TEST_LAB.md` for disposable-VM validation. Do not test packet capture, replay, blocking, or watchlist behavior on networks you do not own or administer.

## Troubleshooting

- Backend cannot connect to DB: confirm Docker is running and `DATABASE_URL` points to `localhost:8080`.
- Smoke returns `401`: set `SMARTIDS_INTERNAL_SERVICE_TOKEN` in root `.env` to match `INTERNAL_SERVICE_TOKEN` in `backend/.env`.
- Smoke returns connection refused: confirm backend is running on the same `--base-url`.
- Frontend cannot reach backend: set `NEXT_PUBLIC_IDS_REST_BASE_URL`, `IDS_REST_BASE_URL`, and `NEXT_PUBLIC_IDS_WS_URL`.
- Live capture fails on Windows: install Npcap and run PowerShell as Administrator.
- Live capture fails on Linux: run the IDS runtime with `sudo`.
- Model prediction disabled: check startup logs for model artifact validation errors and verify `ml/saved_models` matches `FEATURE_COLUMNS`.

## Suggested README Additions Later

- Architecture diagram image or Mermaid flow for contributors.
- API reference table for every backend endpoint.
- Example screenshots of the dashboard.
- Threat-response safety policy matrix for block/watchlist decisions.
- Production deployment guide with TLS, secrets management, and reverse proxy setup.
- Prometheus/Grafana metrics guide once health/metrics endpoints are added.

## License

Distributed under the MIT License. See `LICENSE`.
