# Roadmap

Project planning for SmartIDS: what's next, what's in progress. Source of truth: `backend/CHECKLIST.md` ("Planned"/"In Progress" sections) and `backend/PLAN.md`. For why past decisions were made, see `docs/decisions.md`; for current system shape, see `docs/architecture.md`.

This file does not duplicate the full changelog in `backend/CHECKLIST.md` — only forward-looking items are listed here. Treat `backend/CHECKLIST.md` as the live, more granular source; this is a snapshot as of 2026-07-17.

---

## In Progress

- Smoke the live IDS runtime against the backend ingest path and verify persisted IDS events carry both the XGBoost primary and the custom-decision-tree secondary model outputs end-to-end (`backend/CHECKLIST.md`).
- Burn in `SMARTIDS_FEATURE_EXTRACTION_VALIDATE` (Welford's-algorithm packet-length stats vs. the existing list-based computation) against real/replayed traffic before cutting the extractor over to the incremental values (`backend/CHECKLIST.md`, 2026-07-18 entry).

---

## Completed — Engine Performance / Security / Realtime (2026-07-18)

All 7 workstreams from the approved engine-improvement plan landed; granular log in `backend/CHECKLIST.md`. Summary:

- Fixed unbounded per-source-IP dict growth (`threat_detection/heuristic.py`), added a `SessionBuilder.sessions` lock, replaced silent exception swallowing in `packet_processor.py` with structured logging.
- Closed the `sql-injection/decide` and `/realtime/broadcast*` auth gaps; added SHA-256 pre-load integrity verification for ML model artifacts.
- Hardened engine↔backend auth: standardized on `SMARTIDS_INTERNAL_SERVICE_TOKEN`, added HMAC-SHA256 signing + timestamp + nonce + Redis replay cache.
- Decoupled the secondary (DecisionTree) model onto a bounded worker pool, fire-and-forget — the direct fix for the packet queue's 100% utilization — with matching telemetry/dashboard queue-depth metrics.
- Added the four missing realtime broadcast channels, removed the frontend's redundant 30s poll loop, fixed the hardcoded WS port mismatch.
- Replaced the engine's 1.5s command poll with an optional persistent HMAC-authenticated WebSocket (`SMARTIDS_ENGINE_WS_ENABLED`, default off), keeping the DB-backed queue as durable fallback.
- Landed Welford's-algorithm running stats for packet-length features behind a validate-only flag (see "In Progress" above for the remaining cutover decision); IAT stats intentionally left list-based pending evidence out-of-order arrival can't occur.

---

## Completed — Capture-Level Watch/Exclude Filtering (2026-07-19)

`PacketFilters.build_capture_filter()` (`packet_capture/utils/packet_filters.py`) builds a BPF filter string from allow-list (`SMARTIDS_CAPTURE_WATCH_IPS`/`_PORTS`) and block-list (`SMARTIDS_CAPTURE_EXCLUDE_IPS`/`_PORTS`) env vars, wired into `SnifferService.__init__` (`packet_capture/sniffer_service.py`) in place of the hardcoded `PacketFilters.basic_filter()`. Malformed entries (bad IPv4, out-of-range port) are logged and skipped rather than raised. Defaults to today's exact `"ip"` behavior when nothing is configured — purely additive, no queue/session/feature/ML code touched (libpcap applies the filter before packets reach Python). Part B of `docs/plans/engine-registration-and-capture-filter.md`; Part A (engine registration) remains in Planned below.

---

## Planned

### Engine Registration / Capture Filtering (2026-07-19)

Full design: `docs/plans/engine-registration-and-capture-filter.md`. Sent to Ultraplan for cloud refinement (session `session_01ToEC8FPcQWije7mC3vJ25e`); reconcile any refined version back into that file rather than keeping two copies.

- Browser-based per-engine registration (device-linking style: local temp server + browser approval), issuing a revocable per-engine HMAC credential that **coexists** with the existing global `SMARTIDS_INTERNAL_SERVICE_TOKEN` rather than replacing it. New `engines` table (registration/status/credential management only — deliberately **not** adding per-engine scoping to `ids_events`/`alerts`/`sessions`); phased: (1) registration + local config, (2) heartbeats/WS status/dashboard list, (3) remote policy push, credential rotation, live revocation, local event buffering.

Capture-level IP/port watch/exclude filtering (previously listed here) landed 2026-07-19 — see Completed below.

### ML / Dataset

- Add a CIC IDS 2018 live-compatible training/evaluation entrypoint that consumes the newly prepared outputs, without replacing the CICIDS2017 flow yet.
- Regenerate or replace the bundled CICIDS2017 train/test datasets with verified values for all canonical `FEATURE_COLUMNS`.
- Remove legacy CICIDS2017-specific training/evaluation/preparation paths **after** the CIC IDS 2018 model is trained, verified, and accepted as the primary live-compatible model (not yet — CICIDS2018 is not yet primary).

### Dashboard / Live Data

- Implement the full dashboard live-data architecture: database-first logs, traffic, health, and shared realtime contracts.
- Persist engine telemetry snapshots and expose backend `/logs`, `/traffic`, `/health` query endpoints plus small websocket update envelopes. **Note**: `docs/api.md` shows `GET /logs`, `GET /traffic`, `GET /health/runtime(/history)` already exist and `engine_telemetry_snapshots` is already a persisted table (`docs/database.md`) — this item may be largely complete; verify remaining scope against `backend/CHECKLIST.md` before treating it as untouched.
- Extend persisted IDS event and session query models where needed so logs/traffic pages filter and sort on durable fields instead of derived frontend mock data.
- Migrate frontend live dashboard pages to backend-first REST + websocket + polling adapters and remove the remaining legacy mock helpers from active routes.
- Prepare frontend revamp and custom decision-tree follow-up after database + lab verification.

### Frontend

- Add frontend route middleware for login-required page access.
- Add frontend routing and shared application shell for Dashboard, Threat Reports, Session Logs, and Blocked IPs.

### SQL Injection

- Keep SQL injection feature as placeholder integration only until ML model handoff is complete (development intentionally paused).

### Cleanup

- Keep `backend/smoke/*.py` (and matching README smoke commands) only until the stable cutover is proven, then remove as disposable scaffolding.

---

## Observed Gaps Not Yet Tracked in `backend/CHECKLIST.md`

Cross-referencing `docs/api.md` against the checklist's "service-to-service auth" completion claims:

- ~~`POST /api/v1/realtime/broadcast*` (4 routes) and `POST /api/v1/sql-injection/decide` currently have no auth dependency in the router code.~~ **Resolved 2026-07-18** — `require_internal_service_auth` added to both; see "Completed — Engine Performance / Security / Realtime" above.

---

## Stale Planning Documents

- `AGENTS.md` (root) still frames "Next IDS Engine Implementation" as building capture -> queue -> session builder -> feature extractor -> heuristic/ML detection -> response policy/blocker -> backend reporter from scratch, and lists "backend reporting contracts for session-level IDS events and alerts" as the first implementation focus. Per `docs/architecture.md`, this pipeline is already implemented end-to-end. Treat `AGENTS.md`'s "Current Priority"/"Next IDS Engine Implementation" sections as historical intent, not current planning — reconcile against `backend/CHECKLIST.md` before acting on them.
- `backend/AGENTS.md` states "Mounted REST routers today: `auth` and `api_keys` only" — `backend/app/main.py` currently mounts 15 routers (`docs/api.md`). This note is stale.

---

## Unknown

- No dated release milestones, version targets, or external roadmap tracker found in the repository — all planning evidence is the checklist/plan documents above.
