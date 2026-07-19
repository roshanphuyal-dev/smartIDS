# Architectural Decisions

Rationale behind key design choices in SmartIDS — the *why*, not the *what* (see `docs/architecture.md` for what exists, `docs/roadmap.md` for what's next). Sourced from `AGENTS.md`, `backend/AGENTS.md`, `backend/PLAN.md`, and `backend/CHECKLIST.md`. Where no explicit rationale is documented in the repository, this is stated as Unknown rather than inferred.

---

## Passive detection, reactive mitigation only

**Decision**: SmartIDS captures via `scapy.sniff`, observing packet copies after the OS networking stack; it is explicitly not a kernel-level inline IPS.

**Why**: Because capture happens on copies after the stack has already processed the packet, mitigation (blocking) can only affect *future* traffic from a source, never the triggering packet itself. `AGENTS.md` is explicit that the system must never be described as perfect prevention or inline packet blocking — this is a factual capability constraint, not a preference.

**Source**: `AGENTS.md` (Project Identity).

---

## Single backend, web-first; desktop reuses the same modules

**Decision**: Replaced an earlier dual-architecture plan with one backend serving the web dashboard as the primary target; desktop support (if built) must reuse the same backend modules via a local runtime/profile rather than a separate desktop backend or adapter framework.

**Why**: Avoid maintaining two backend implementations or an adapter abstraction layer for a desktop use case that isn't concretely required yet.

**Source**: `backend/PLAN.md` (Goal, Product Priority); `backend/CHECKLIST.md` change log, 2026-05-28 ("replaced dual-architecture plan with single-backend, web-primary roadmap").

---

## One canonical ML feature schema

**Decision**: `ml/features/schema.py::FEATURE_COLUMNS` is the single source of truth for dataset cleaning, training, evaluation, model saving, and live extraction. Never duplicate feature lists across files. Never train on a feature the live packet/session pipeline can't honestly produce.

**Why**: Prevents train/serve skew — a model trained on columns the live pipeline can't actually compute would silently degrade or fail at inference time. `src_port` is deliberately excluded as an ML feature (session-key only) since it doesn't carry signal; `dst_port` is kept.

**Source**: `AGENTS.md` (ML Runtime Contract); enforced by `ml/runtime/artifact_validation.py` and tests under `tests/unit/ml/`.

---

## Fail-fast model loading

**Decision**: The live predictor validates runtime model artifacts against the canonical feature schema at startup and fails fast (disables prediction) rather than serving predictions against a mismatched schema/artifact.

**Why**: Silent schema drift between training and runtime would produce wrong predictions without any visible error — failing fast surfaces the problem immediately instead.

**Source**: `backend/CHECKLIST.md` ("Validate runtime model artifacts...", "Make live predictor startup fail fast...").

---

## Minimal packet-capture hot path

**Decision**: `LiveSniffer`'s packet callback (`_handle_packet`) does parse + enqueue only — no ML inference, DB writes, network calls, file I/O, or other blocking work runs inside it.

**Why**: `scapy.sniff(...)` is blocking and runs in a dedicated thread; any slow work in the callback risks dropped packets under load. Heavier work (session building, feature extraction, prediction, forwarding) happens downstream in `PacketProcessor`, off the capture thread.

**Source**: `AGENTS.md` (Capture Architecture Constraint).

---

## Additive, opt-in runtime integrations

**Decision**: New engine components (backend reporting, command polling, telemetry forwarding) are wired in only when their corresponding environment variable is set (e.g. `SMARTIDS_IDS_EVENT_ENDPOINT`, `SMARTIDS_COMMANDS_ENDPOINT`) — `SnifferService.__init__` conditionally constructs each forwarder/poller.

**Why**: Preserve the already-working IDS capture/detection path while incrementally adding backend integration, rather than making the capture pipeline hard-depend on the backend being reachable.

**Source**: `AGENTS.md` (Current Priority: "Preserve the current working IDS process while adding small, opt-in engine components around it").

---

## Layered backend feature modules

**Decision**: Every backend feature follows `router -> dependencies -> service -> repository -> models/schemas`; routers stay thin, business logic lives in services, DB access is confined to repositories; service/repository layers raise app-specific exceptions rather than raw `HTTPException`.

**Why**: Consistent separation of HTTP concerns from business logic and data access, applied uniformly so new features (e.g. `sql_injection`, `realtime`) don't couple to unrelated ones like `auth`/`api_keys`.

**Source**: `backend/AGENTS.md` (Style Contract, Current Backend Shape); `backend/PLAN.md` (Current Backend Shape).

---

## WebSocket for ML → backend → frontend, with store/broadcast split

**Decision**: Realtime delivery from the ML runtime to the dashboard uses a WebSocket channel (`/api/v1/realtime/ws`). Each accepted message is split into (a) a durable, normalized DB record and (b) a sanitized, frontend-safe broadcast payload — raw/internal/debug fields are never forwarded to the frontend.

**Why**: Low-latency streaming for the dashboard, while keeping persistence authoritative and untrusted/internal model output out of client-facing payloads.

**Source**: `backend/AGENTS.md` (Realtime Data Flow Contract, Realtime Payload Requirements).

---

## Internal-service-token auth, separate from user sessions

**Decision**: Endpoints the IDS runtime itself calls (`ids-events`, `sessions/upsert`, `block-events/upsert`, `engine-telemetry`, `engine-commands*`, `realtime/broadcast*`, `sql-injection/decide`) are protected by `require_internal_service_auth` (`backend/app/common/internal_auth.py`), distinct from the cookie-based user-session auth used by browser clients.

**Why**: These are service-to-service calls with no browser/user context; reusing session-cookie auth wouldn't fit, and treating them as fully open would leave operational ingest endpoints unauthenticated. A prior incident (`backend/CHECKLIST.md`, 2026-07-12) where the two tokens drifted out of sync caused 401s on internal ingest — confirms this is treated as a hard dependency, not a nicety.

**Source**: `backend/CHECKLIST.md` ("Add explicit service-to-service auth for IDS ingest..."); `.env.example` (`SMARTIDS_INTERNAL_SERVICE_TOKEN`).

**Superseded in part** — see "HMAC-signed shared secret, not bare-token comparison" below: the mechanism changed from a plain header-equality check to HMAC-SHA256 signing + Redis-backed nonce replay, and the `/realtime/broadcast*`/`/sql-injection/decide` auth gap noted here previously is now closed.

---

## HMAC-signed shared secret, not bare-token comparison

**Decision**: The internal-service token is no longer sent on the wire and compared with `!=`. It is used only as an HMAC-SHA256 key: every request is signed over method, path+query, a SHA-256 hash of the body, a timestamp, and a per-request nonce (`x-smartids-signature`/`x-smartids-timestamp`/`x-smartids-nonce`), verified with `hmac.compare_digest` plus a ±30s freshness window and a Redis `SET NX EX 60` nonce replay cache. The same primitive (`verify_internal_ws_signature`) is reused for the engine↔backend command WebSocket's handshake, signing a fixed stand-in method/path since a WS handshake has no real HTTP request to sign.

**Why**: A bare `!=` token comparison is a timing-attack surface and gives no replay protection — a captured request/header could be resent indefinitely. HMAC signing plus a nonce cache closes both gaps with one shared secret, still generated the same way (`openssl rand -hex 32`). `Settings` now also refuses to boot in production with an unset/weak (<64 char) token, making the fail-closed behavior structural rather than a runtime check that could be skipped; outside production an empty token is kept as an explicit, loudly-logged dev-only bypass rather than a silent no-op, preserving local-dev ergonomics.

**Consequence, deliberately accepted**: a coordinated engine+backend redeploy is required (old engine can't auth to a new backend and vice versa) — no legacy/dual-mode compatibility shim was added, since there was no evidence of a rolling-deploy requirement across independently-versioned engine/backend instances.

**Source**: `docs/roadmap.md` (Completed — Engine Performance / Security / Realtime, 2026-07-18); `backend/app/common/internal_auth.py`, `backend/app/core/config.py`.

---

## In-process thread pool for secondary-model dispatch, not Celery

**Decision**: The secondary (shadow) model's inference is dispatched to a bounded, in-process `ThreadPoolExecutor`-shaped worker pool (parametrized `BackgroundPublisher`, `SMARTIDS_SECONDARY_MODEL_WORKERS`/queue size), not routed through the existing Celery/Redis task queue the backend already runs for email/geolocation.

**Why**: Celery adds network latency (broker round-trip) unsuitable for a per-packet real-time path. Threads (not `ProcessPoolExecutor`) were chosen because `ml/runtime/custom_decision_tree_runtime.py`'s `install_runtime_aliases()` monkeypatches `sys.modules["__main__"]` for `joblib` deserialization — a process-local trick that would need re-running per subprocess and would multiply model memory N×. The custom decision tree's predict path is pure-Python and does contend for the GIL, but a single-row tree walk is microseconds and the call is fire-and-forget, so bounded contention is an explicit, accepted trade-off against the alternative (fully synchronous, blocking the packet-queue consumer).

**Consequence**: the secondary-model callback is structurally isolated (a standalone `SecondaryShadowEventPublisher`, constructed with no reference to `PacketProcessor`) so it can only publish shadow-prediction events, never call into `auto_blocker`/`_publish_block_event`/`session_builder` — preventing a late-arriving async result from ever reaching the order-sensitive session-upsert or alerting paths.

**Source**: `docs/roadmap.md` (Completed — Engine Performance / Security / Realtime, 2026-07-18); `packet_capture/processor/packet_processor.py`, `ml/runtime/live_predictor.py`/`completed_flow_predictor.py`.

---

## Engine↔backend WebSocket is a latency optimization, not a replacement for the durable command queue

**Decision**: `packet_capture/realtime/engine_ws_client.py` (opt-in via `SMARTIDS_ENGINE_WS_ENABLED`) pushes block/unblock commands to the engine over a persistent authenticated WebSocket, but the DB-backed `engine_commands` table remains the source of truth — the client still performs one `GET /engine-commands` catch-up poll on every connect/reconnect before relying on WS push, and command acks still flow through the same ack path either way.

**Why**: A WebSocket push is strictly a latency win over the previous 1.5s poll loop; treating it as a full replacement would lose commands issued while the engine is disconnected, since WS delivery has no persistence of its own. Default is off, and the old poll loop is unchanged unless explicitly enabled, so this is an additive rollout, not a cutover.

**Source**: `docs/roadmap.md` (Completed — Engine Performance / Security / Realtime, 2026-07-18; "staged `SMARTIDS_ENGINE_WS_ENABLED` rollout" under In Progress); `docs/architecture.md` (Packet / Data Flow).

---

## SQL injection detection kept as an isolated, paused feature module

**Decision**: SQL injection detection (`backend/app/features/sql_injection/`) is built as its own feature-module boundary, isolated from auth/API-key/realtime code, and development is currently paused — only extension points (contracts, placeholder decision endpoint) are kept.

**Why**: This repository is also the merge target for a separate SQL injection detection workstream (proxy-routed client SQL requests: `client -> proxy -> detection service -> decision -> downstream server`). Isolating it as its own module means the merge won't require touching existing auth/realtime logic; pausing it reflects that the ML model handoff for this path isn't ready yet.

**Source**: `backend/AGENTS.md` (SQL Injection Merge Context); `backend/CHECKLIST.md` ("Scope change: SQL injection development paused...", "Keep SQL injection feature as placeholder...").

---

## Frontend migrated off direct database writes

**Decision**: The frontend (`frontend/`) no longer writes to Postgres directly for API keys, threat responses, SQL-injection actions, or notification read-state — those now go through backend REST endpoints. The frontend retains a Drizzle schema/read path against the same database for some reads.

**Why**: Consolidate on one canonical database with the backend as the sole writer, avoiding two independent write paths (frontend Drizzle + backend SQLAlchemy) diverging on the same tables.

**Source**: `backend/CHECKLIST.md` ("Consolidate the project onto a single canonical database...", "Migrate API-key CRUD from frontend DB access to backend API calls", "Confirm the frontend remains read-only...").

**Consequence, not fully resolved**: the frontend's Drizzle schema (`threats`, `analytics_snapshots`) has drifted from the backend's actual Alembic-migrated tables — see `docs/database.md` (Frontend Schema Drift). No documented decision covers reconciling this drift; treat it as an open item, not a settled design.

---

## "Threats" is a view over `Alert`, not its own table

**Decision**: There is no separate `threats` table; `GET /api/v1/threats*` queries the `alerts` table directly, matching on either `Alert.threat_id` or `Alert.id`.

**Why**: Unknown — no repository document states the rationale explicitly (plausibly: avoids duplicating alert lifecycle/dedup state into a second table, but this is not confirmed by any source, so it is not asserted as fact).

**Source**: `backend/app/features/threats/repository.py`.

---

## Engine-command dedupe is process-local, not durable

**Decision**: The runtime's processed-command dedupe (`response_engine/processed_command_store.py`) is documented as process-local only rather than made durable/persistent.

**Why**: Explicit trade-off recorded in the checklist — durability was considered and the simpler process-local approach was chosen and documented as a known limitation instead.

**Source**: `backend/CHECKLIST.md` ("Make processed engine-command dedupe durable or document it as process-local only" — done via documentation, not durability).

---

## Bounded in-memory/file-backed state for IP activity

**Decision**: `IPActivityTracker` bounds tracked IPs, action history, and file-backed entries via `SMARTIDS_IP_ACTIVITY_MAX_TRACKED_IPS`, `SMARTIDS_IP_ACTIVITY_MAX_ACTION_HISTORY`, `SMARTIDS_IP_ACTIVITY_MAX_FILE_ENTRIES`, with periodic file compaction.

**Why**: Prevent unbounded memory/disk growth in a long-running capture process.

**Source**: `backend/CHECKLIST.md` ("Bound in-memory IP activity state and add retention or cleanup for file-backed activity logs"); `.env.example`.
