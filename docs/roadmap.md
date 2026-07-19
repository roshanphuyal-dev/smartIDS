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

## Planned

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
