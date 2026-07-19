# Architecture

System design for SmartIDS. Full endpoint list: `docs/api.md`. Full table/column detail: `docs/database.md`. Setup/commands: `docs/environment.md`. Rationale behind these choices: `docs/decisions.md`.

---

## System Overview

SmartIDS is a **passive, userland intrusion detection system with automated reactive mitigation** — not a kernel-level inline IPS. `scapy` observes packet copies after the OS networking stack, so mitigation can only block *future* traffic, never the packet that triggered detection (`AGENTS.md`).

| Component | Path | Responsibility |
|-----------|------|-----------------|
| Packet Capture | `packet_capture/` | Live packet sniffing, parsing, queueing, forwarding to backend |
| Traffic Engine | `traffic_engine/` | Session/flow building from packets |
| Feature Engine | `feature_engine/` | Converts sessions into the canonical ML feature vector |
| ML | `ml/` | Feature schema, training, evaluation, runtime prediction |
| Threat Detection | `threat_detection/` | Heuristic (non-ML) detection |
| Response Engine | `response_engine/` | Blocking decisions, firewall adapters, backend command polling |
| Backend | `backend/` (submodule, FastAPI) | Ingestion, persistence, auth, realtime delivery, SQL-injection decision audit |
| Frontend | `frontend/` (submodule, Next.js) | Dashboard UI, realtime display |
| Replay / Tools | `replay/`, `tools/` | Offline replay of CICIDS CSVs against the running pipeline |

Two independent detection flows converge on the backend: the **IDS pipeline** (packet capture → ML/heuristic → events/alerts/sessions) and **SQL injection detection** (proxy-routed client SQL requests → decision audit), described separately below. They share the backend's persistence/auth infrastructure but are otherwise isolated feature modules.

---

## Packet / Data Flow

```
packet_capture.main
  -> SnifferService
       -> LiveSniffer (scapy.sniff, dedicated thread, minimal callback: parse + enqueue)
       -> Queue (maxsize 10000)
       -> PacketProcessor (consumer)
            -> traffic_engine.SessionBuilder  (packets -> TrafficSession, keyed by session_key)
            -> feature_engine.SessionFeatureExtractor (TrafficSession -> FEATURE_COLUMNS vector)
            -> ml.runtime.LivePredictor / CompletedFlowPredictor (ModelStack: primary + secondary model)
            -> threat_detection.HeuristicDetector (non-ML rule check)
            -> response_engine.AutoBlocker -> firewall adapter (Linux/Windows) + IPActivityTracker
            -> response_engine.BackendCommandPoller (pulls manual block/unblock commands from backend; still the only path when `SMARTIDS_ENGINE_WS_ENABLED` is unset)
            -> packet_capture.realtime.EngineWSClient (optional, `SMARTIDS_ENGINE_WS_ENABLED=true`: persistent authenticated WS push in place of the 1.5s poll; still does one `GET /engine-commands` catch-up per (re)connect, so the DB-backed queue stays the durable source of truth)
       -> packet_capture.forwarding.* (BackgroundPublisher, per-endpoint queues)
            -> FastAPI backend (HTTP, internal-service-token authenticated)
                 - IDS events, alerts, session upserts, block events, engine telemetry
  -> backend persists + broadcasts over WebSocket (`/api/v1/realtime/ws`)
       -> frontend dashboard (Next.js, realtime hooks + REST polling)
```

`SnifferService.__init__` (`packet_capture/sniffer_service.py`) wires this: it conditionally constructs one `FastAPI*Forwarder` + `BackgroundPublisher` per configured `SMARTIDS_*_ENDPOINT` env var, and only starts a `BackendCommandPoller` if `SMARTIDS_COMMANDS_ENDPOINT` is set — every forwarding/polling integration is additive and opt-in. Command delivery has a second, opt-in transport: if `SMARTIDS_ENGINE_WS_ENABLED=true` and `SMARTIDS_ENGINE_WS_URL` is set (and a signer is configured), `SnifferService.start()` starts an `EngineWSClient` (`packet_capture/realtime/engine_ws_client.py`) instead of the poll thread — a persistent, HMAC-authenticated WebSocket to the backend's `/api/v1/realtime/engine-ws`. It is a latency optimization only: the DB-backed `engine_commands` table remains the durable queue, and the client performs one `GET /engine-commands` catch-up poll (reusing `BackendCommandPoller`) on every connect/reconnect before relying on WS push. Default is off, so the 1.5s poll loop is unchanged unless explicitly enabled.

### Capture Layer (`packet_capture/`)

- `sniffers/live_sniffer.py` — `LiveSniffer` wraps blocking `scapy.sniff(...)` in a dedicated thread. Its packet callback is intentionally minimal: parse + enqueue only (no ML inference, DB writes, network calls, or blocking work — see `docs/coding-standards.md`).
- `sniffers/interface_manager.py` — resolves the capture interface (override via `SMARTIDS_CAPTURE_INTERFACE`).
- `parsers/packet_parser.py`, `packet_models/` — parses raw packets into `PacketData`/`ProtocolType`.
- `processor/packet_processor.py` — the queue consumer; drives session building, feature extraction, prediction, heuristic check, and response/forwarding per packet.
- `forwarding/` — one forwarder class per backend integration point (`fastapi_alert_forwarder.py`, `fastapi_ids_event_forwarder.py`, `fastapi_session_update_forwarder.py`, `fastapi_block_event_forwarder.py`, `fastapi_engine_telemetry_forwarder.py`), each wrapped in a `BackgroundPublisher` (bounded async queue, drop-with-log-every-N on overflow via `SMARTIDS_FORWARDER_QUEUE_SIZE`/`SMARTIDS_FORWARDER_DROP_LOG_EVERY`).
- `telemetry/engine_telemetry.py` — `EngineTelemetryCollector` tracks packet counts, queue health, active sessions, ML rate; periodically forwarded to the backend (`SMARTIDS_ENGINE_TELEMETRY_INTERVAL_SECONDS`, default 30s).

### Traffic Engine (`traffic_engine/`)

- `session_builder/session_builder.py` — `SessionBuilder` groups packets into `TrafficSession` objects keyed by `session_key.py` (source/destination IP+port+protocol). `src_port` is part of the session key only, never an ML feature; `dst_port` is an allowed ML feature.
- Sessions expire on FIN, RST, idle timeout, or max duration (recommended defaults: 30s idle, 120s max).
- Supports repeated prediction during an active session, not just at flow completion (minimum triggers: age >= 1s, packet_count >= 5, periodic windows, and flow end).

### Feature Engine (`feature_engine/`)

- `extractors/session_feature_extractor.py` — `SessionFeatureExtractor.extract(session)` returns exactly `ml/features/schema.py::FEATURE_COLUMNS`, no extras, no missing fields.
- `stats.py` — safe statistics helpers (min/max/mean/std/variance/rate/IAT) that return a neutral `0` instead of NaN/inf when a value can't be safely computed.
- `feature_store/feature_store.py`, `schema/features_mapping.py` — feature storage/mapping support.

### Threat Detection (`threat_detection/`)

- `heuristic.py` — `HeuristicDetector`, a non-ML rule-based detection path running alongside the ML predictors.
- `backend/app/engine/path_traversal_detector_engine.py` — a backend-side heuristic detector (`PathTraversalDetector`), separate from the runtime engine's `threat_detection/` module.

### Response Engine (`response_engine/`)

- `auto_blocker.py` — `AutoBlocker`, decides and executes automatic mitigation given a detection result.
- `firewall/` — `base.py` (interface), `factory.py` (platform selection), `linux_adapter.py`, `windows_adapter.py` — OS-specific firewall rule adapters.
- `policy.py` — block/watchlist decision policy.
- `ip_activity_tracker.py` — bounded in-memory + JSONL-file-backed (`logs/ip_activity.jsonl`) history of blocked/watchlisted IP activity (`SMARTIDS_IP_ACTIVITY_*` env vars bound its size).
- `backend_command_poller.py` — `BackendCommandPoller`, polls the backend for manually-issued block/unblock/watchlist commands and executes them; deduplicates via `processed_command_store.py` (process-local, documented as such rather than made durable — see `docs/decisions.md`).

---

## ML Pipeline

- **Canonical schema contract**: `ml/features/schema.py::FEATURE_COLUMNS` is the single source of truth. Dataset prep, training, evaluation, saved artifacts, and live extraction all import it — never a duplicated feature list (enforced by tests in `tests/unit/ml/`).
- **Datasets** (`ml/datasets/`): CICIDS2017 and CICIDS2018 loaders/preparers/splitters, each mapped through `ml/features/{cicids2017,cicids2018}_mapping.py` and validated via matching `*_validation.py` modules.
- **Training** (`ml/training/`): `build_cicids2017_model.py` (build → evaluate → verify → atomic activation, one command); `train_cicids2017.py` (legacy); `train_cicids2017_live_compatible.py`, `train_xgboost_cicids2018.py`, `train_cicids2018_live_compatible.py` (live-compatible / CICIDS2018 path, in progress — see `docs/roadmap.md`).
- **Models** (`ml/models/`): `sklearn_model.py` (custom decision tree), `xgboost_model.py`.
- **Runtime** (`ml/runtime/`): `live_predictor.py` and `completed_flow_predictor.py` perform inference; `model_stack.py` combines a primary model (XGBoost) with a secondary model (custom decision tree); `artifact_validation.py` validates saved artifacts against the canonical schema before prediction and fails fast / disables prediction on mismatch.
- **Evaluation** (`ml/evaluation/`): per-class metrics, confusion matrix, and false-positive-rate reporting for the Normal Traffic class (`metrics.py`).

Cross-cutting constraint: protocol is always numeric (TCP=6, UDP=17, ICMP=1, UNKNOWN=0); no NaN/inf may reach the model; the pipeline never trains on a feature the live path can't honestly produce.

---

## SQL Injection Detection Architecture

A **second, independent detection flow**, isolated from the packet-capture IDS pipeline above. Intended shape (`backend/AGENTS.md`, SQL Injection Merge Context):

```
client -> proxy -> [external] detection service -> decision -> downstream app/data server
                                     |
                                     v
                     POST /api/v1/sql-injection/decide  (backend/app/features/sql_injection/)
                                     |
                                     v
                     sql_injection_events table (audit record)
```

- **Current implementation is audit-only, not detection**: `SQLInjectionService.decide()` (`backend/app/features/sql_injection/service.py`) does **not** run any injection-detection logic itself. It trusts the caller's `payload.detected` boolean (and `confidence`/`reason`), derives `decision = "block" if detected else "allow"` and `http_status = 400 if detected else 200`, persists a `SQLInjectionEvent` row (truncating the raw query to a 255-char `query_preview`), and returns the same decision. It is idempotent on `request_id` — a repeat request_id returns the previously stored decision without re-evaluating.
- The actual detection model/service that produces `detected`/`confidence` is external to this repository — this endpoint is the recording/decision-relay point the merge target (a companion SQL injection detection project) is expected to call.
- Kept as its own feature module (`app/features/sql_injection/`: `router.py`, `service.py`, `repository.py`, `models.py`, `schemas.py`) specifically so this merge doesn't require touching `auth`, `api_keys`, or `realtime` code (`docs/decisions.md`).
- Status: development paused; kept as a placeholder/extension point until the ML model handoff for this path is ready (`backend/CHECKLIST.md`; `docs/roadmap.md`).
- Route: `POST /api/v1/sql-injection/decide` — currently has **no auth dependency** in the router code (see Authentication, below, and `docs/api.md`).
- Data model: `sql_injection_events` table (`docs/database.md`) — `request_id` (unique), `ts`, `source`, `query_preview`, `detected`, `confidence`, `reason`, `decision`, `http_status`.

---

## Backend Architecture

FastAPI service (`backend/`, submodule `ids-api`) — the control, persistence, and realtime-delivery layer for both detection flows.

**Layering convention**, applied per feature: `router -> dependencies -> service -> repository -> models/schemas` (see `docs/coding-standards.md`). Routers stay thin; business logic lives in services; DB access is confined to repositories; service/repository layers raise `AppException` subclasses rather than raw `HTTPException` (`app/common/exceptions.py`, centrally mapped in `app/common/exception_handlers.py`).

Feature modules (`backend/app/features/`): `auth`, `api_keys`, `user_sessions`, `ids_events`, `alerts`, `realtime`, `sessions`, `traffic`, `logs`, `health`, `sql_injection`, `engine_commands`, `engine_telemetry`, `block_events`, `blocked_ips`, `notifications`, `dashboard`, `threats`, `analytics_rollups`, `geolocation`, `ip_control_state`. All routers mount under `/api/v1` (`backend/app/main.py`).

Every success response is wrapped by `create_response()` (`app/common/responses.py`): `{ data, message, meta: { timestamp, request_id } }`.

---

## API Layer

Full endpoint-by-endpoint reference: `docs/api.md`. Summary by access pattern:

| Access pattern | Who calls it | Example routes |
|----------------|--------------|----------------|
| Session-authenticated REST | Frontend dashboard (browser, cookie) | `/dashboard/*`, `/blocked-ips`, `/sessions`, `/threats`, `/notifications`, `/api-keys` |
| Internal-service-authenticated REST | IDS runtime (`packet_capture`/`response_engine` forwarders/pollers) | `/ids-events` (POST), `/sessions/upsert`, `/block-events/upsert`, `/engine-telemetry`, `/engine-commands*`, `/realtime/broadcast*`, `/sql-injection/decide` |
| Internal-service-authenticated WebSocket | IDS runtime (`packet_capture/realtime/engine_ws_client.py`), opt-in via `SMARTIDS_ENGINE_WS_ENABLED` | `/realtime/engine-ws` (first frame is a signed `auth` envelope, verified the same way as the REST routes above, plus Redis nonce replay check; unauthenticated frames get the connection closed) |
| Unauthenticated (no dependency found) | Frontend dashboard's push channel | `/realtime/ws` |
| Public (pre-auth) | Anonymous browser clients | `/auth/register`, `/auth/login`, `/auth/oauth/*`, `/auth/forgot-password`, `/auth/reset-password` |

---

## Database Architecture

PostgreSQL 16 (`backend/docker-compose.yml`), accessed via async SQLAlchemy (`asyncpg`); Alembic-migrated (`backend/migrations/`). Full column-level detail: `docs/database.md`.

- All tables share `CUIDMixin` (CUID2 string primary key) + `TimestampMixin` (`created_at`/`updated_at`) (`app/db/base.py`).
- Core groups: **auth** (`users`, `oauth_accounts`, `sessions`, `api_keys`), **IDS pipeline data** (`network_sessions`, `ids_events`, `alerts`, `block_events`, `engine_commands`, `engine_telemetry_snapshots`, `ip_control_states`, `network_threat_rollups`), **SQL injection audit** (`sql_injection_events`), **dashboard support** (`notifications`, `ip_locations`).
- "Threats" is a query-time view over the `alerts` table, not its own table — `GET /api/v1/threats*` queries `Alert` directly.
- The frontend holds a separate Drizzle schema (`frontend/src/lib/db/schema.ts`) against the same database for some read paths; it has drifted from the backend's Alembic-migrated tables (its `threats`/`analytics_snapshots` tables have no backend migration) — see `docs/database.md` (Frontend Schema Drift).

---

## Authentication

Two independent auth mechanisms, used for different callers:

### 1. User session (browser clients)

- Login/register: `app/features/auth/service.py`; passwords hashed with **argon2** (`app/features/auth/password.py::hash_password`/`verify_password`).
- Session token issued on login, stored server-side in the `sessions` table (`token_hash`, `expires_at`, `revoked_at`, `user_agent`, `ip_address`), and sent to the client as an **HttpOnly cookie** (`SESSION_COOKIE_NAME`, default `session_token`) — `set_session_cookie()`/`clear_session_cookie()` (`app/features/auth/dependencies.py`). Cookie flags come from config: `SESSION_TTL_SECONDS` (default 604800 = 7 days), `SESSION_COOKIE_SECURE` (default `false`), `SESSION_COOKIE_SAMESITE` (default `lax`).
- `get_current_user`/`get_current_auth_session` (`app/features/auth/dependencies.py`) resolve the token from **either** the session cookie **or** an `Authorization: Bearer <token>` header (`_extract_session_token`) — both paths are accepted for the same session mechanism.
- OAuth: GitHub via Authlib (`app/features/auth/oauth/github.py`, `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`/`GITHUB_REDIRECT_URI`), state TTL `OAUTH_STATE_TTL_SECONDS` (default 600s); links to an `oauth_accounts` row, unique on `(provider, provider_user_id)`.
- Email verification and password reset use time-limited signed tokens (`verification_tokens.py`, `reset_tokens.py`) delivered via the configured email provider.

### 2. Internal service token (IDS runtime → backend)

- `require_internal_service_auth` (`app/common/internal_auth.py`) requires an HMAC-SHA256 signature (`x-smartids-signature`), timestamp (`x-smartids-timestamp`, ±30s window), and single-use nonce (`x-smartids-nonce`, checked against a Redis `SET NX EX 60` replay cache) on every request — not a bare token comparison. The signing string is `f"{method}\n{path_with_query}\n{sha256(body).hexdigest()}\n{timestamp}\n{nonce}"`, HMAC'd with the shared secret (`settings.SMARTIDS_INTERNAL_SERVICE_TOKEN`) and compared via `hmac.compare_digest`. The engine side signs with the matching `packet_capture/auth/request_signer.py::InternalRequestSigner`.
- **Production**: `Settings` refuses to boot if `SMARTIDS_INTERNAL_SERVICE_TOKEN` is unset or under 64 chars (256 bits) — fail-closed by construction, not by a runtime check. **Non-production**: an empty token is treated as an explicit dev-only bypass (logged as a warning on every request) rather than a silent no-op.
- If the Redis replay cache itself is unreachable, the dependency raises `ServiceUnavailableException` (503) rather than either failing open or crashing — distinct from a rejected (replayed/invalid) request.
- Applied to: `POST /ids-events`, `sessions/upsert`, `block-events/upsert`, `engine-telemetry`, `engine-commands*` (queue/poll/ack), `/realtime/broadcast*` (4 routes), `/sql-injection/decide`.
- The engine<->backend command WebSocket (`/realtime/engine-ws`, `app/features/realtime/engine_ws_router.py`) reuses the same verification primitive (`verify_internal_ws_signature` in `app/common/internal_auth.py`) for its handshake, signing a fixed stand-in method/path (`ENGINE_WS_AUTH_METHOD`/`ENGINE_WS_AUTH_PATH` in `app/features/realtime/engine_ws_schemas.py`) since there is no real HTTP request to sign during a WS handshake; a Redis-unavailable error closes the socket with a distinct code (`4503`) instead of crashing the handshake.
- **Not applied to** `/realtime/ws` — the frontend-facing push channel, a different auth model (browser/session, not service-to-service); see WebSocket Flow, above.

### 3. API keys

- User-scoped, environment-tagged (`live`/`test`/`development`) credentials (`api_keys` table, `key_id` public + one-way `key_hash`), managed via session-authenticated CRUD (`/api-keys*`). Not currently wired into any route's auth dependency — no router checks an API key on inbound requests; they appear to be issued for external/future consumption rather than backend-internal use. Confirm before relying on this for access control.

---

## WebSocket Flow

- Single channel: `GET /api/v1/realtime/ws` (`app/features/realtime/router.py`). Clients connect and are registered with `realtime_manager`; the handler otherwise just drains incoming text frames and deregisters on disconnect — it does not process client-sent messages.
- Server-to-client delivery is push-only, triggered by internal `POST /realtime/broadcast*` calls (from backend services after persisting IDS/session/blocked-IP/dashboard-metric changes), not by anything the WebSocket client sends.
- Each broadcast type has its own sanitized schema (`RealtimeAlertMessage`, `RealtimeSessionMessage`, `RealtimeBlockedIPMessage`, `RealtimeDashboardMetricsMessage`) — only frontend-relevant fields are included; raw/internal model output is never forwarded (`backend/AGENTS.md` Realtime Payload Requirements).
- Frontend: `frontend/src/lib/realtime/use-dashboard-realtime.ts` connects to `NEXT_PUBLIC_IDS_WS_URL` and updates dashboard state from incoming broadcast messages.

---

## Frontend Architecture

Next.js 16 / React 19 dashboard (`frontend/`, submodule `ids-web`).

- Pages under `frontend/src/app/(dashboard)/`: `overview`, `threats`, `sessions`, `blocked-ips`, plus others per `docs/roadmap.md` (shared app shell/routing still in progress).
- Backend access: REST via `frontend/src/lib/backend/*.ts` client wrappers (one per resource — `threats.ts`, `sessions.ts`, `blocked-ips.ts`, `api-keys.ts`, `dashboard.ts`), pointed at `NEXT_PUBLIC_IDS_REST_BASE_URL`/`IDS_REST_BASE_URL`; realtime via `use-dashboard-realtime.ts` (WebSocket, above).
- Direct DB access: `frontend/src/lib/db/` (Drizzle ORM) still exists for some reads (`queries/*.ts`), pointed at the same Postgres instance. Per `backend/CHECKLIST.md`, writes have been migrated off this path onto the backend REST API — see `docs/decisions.md` for why, and `docs/database.md` for the resulting schema drift between the frontend's Drizzle schema and the backend's Alembic-migrated tables.
- UI components: `shadcn`/`@base-ui/react`, `recharts` for charts, Tailwind v4.

---

## Dependencies

### Python (root / ML / packet capture — `config/requirements.txt`)

`fastapi`, `uvicorn` (also pinned per-service in `backend/requirements.txt`), `scapy` (capture/parsing), `pandas`/`numpy`/`scipy` (feature/dataset processing), `scikit-learn`/`xgboost`/`joblib` (training/eval/serialization), `pydantic` (schema validation). Windows-specific pins: `config/requirements_windows.txt`.

### Backend (`backend/requirements.txt`)

`fastapi`, `uvicorn`, `alembic`, `asyncpg`, async SQLAlchemy, `celery`, `Authlib` (OAuth), `argon2-cffi` (password hashing), `cryptography`.

### Frontend (`frontend/package.json`)

`next` 16.2.6, `react`/`react-dom` 19.2.4, `drizzle-orm`/`pg` (DB read path), `recharts` (charts), `shadcn`/`@base-ui/react` (UI), `tailwindcss` v4, `eslint`/`eslint-config-next`, `typescript`.

Full dependency purpose/version table: `docs/environment.md`.

---

## External Services

| Service | Used for | Config |
|---------|----------|--------|
| GitHub OAuth | User login via GitHub identity | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI` |
| Resend (email) | Verification, password-reset, OAuth-account-notice emails, sent async via Celery | `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM` |
| freeipapi (geolocation) | IP-to-location resolution for session `ip_locations` records | `GEOLOCATION_PROVIDER=freeipapi` |
| PostgreSQL 16 (Docker) | Primary datastore | `backend/docker-compose.yml`, `DATABASE_URL` |
| Redis 7 (Docker) | Celery broker + result backend | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` |
| pgAdmin (Docker) | DB browser UI | `backend/docker-compose.yml`, port 5050 |
| Flower (Docker) | Celery task monitor UI | `backend/docker-compose.yml`, port 5555 |

No other third-party APIs found in the codebase.

---

## Replay / Tools

`tools/replay_cicids_csv.py`, `replay/` — replay CICIDS CSV rows as if they were live packets/events, for offline pipeline testing without live capture.
