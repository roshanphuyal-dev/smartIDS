# Code Review Fixes — 2026-07-22

Source: `/code-review` high-effort pass (8 finder angles + verifier) over the
uncommitted working-tree diff in `backend/` and `frontend/` submodules, run
2026-07-22. All 10 findings below were independently confirmed by a verifier
agent against the actual code. Nothing has been fixed yet — start here.

Scope reviewed: uncommitted changes in `backend` (15 files, +210/-9) and
`frontend` (21 files, +303/-593), plus a new untracked migration
(`backend/migrations/versions/f7a91c3e5d02_add_alert_detection_fields.py`)
and new untracked frontend files (`src/middleware.ts`,
`src/components/dashboard/detail-field.tsx`,
`src/lib/hooks/{use-detail-fetch,use-action-feedback,use-time-mode}.ts`).

Re-check `git diff --stat` in both submodules before starting — if this
doesn't match the numbers above, the diff has moved and line numbers below
may have shifted.

---

## Priority order (fix top to bottom)

### 1. Rate-limit key can leak without TTL → permanent lockout
- **File:** `backend/app/features/engines/dependencies.py:47-52`
- **Problem:** `incr(key)` then `expire(key, ...)` share one `try`. If `incr`
  succeeds but `expire` raises `RedisError`, the `except` swallows it and
  returns — the key now has no TTL and persists forever. Every later request
  from that IP keeps incrementing the now-permanent counter; once past the
  max-attempts threshold (5), `POST /engines/register/init` 429s that IP
  forever until someone manually `DEL`s the key or Redis restarts without
  persistence.
- **Fix approach:** Set the TTL unconditionally before or via a single
  pipelined `MULTI`/`EXEC` (or `redis.incr` + `redis.expire` via a Lua script
  / `SET key 1 EX window NX` + fallback `INCR`), so a partial failure can't
  leave an unexpiring key. Simplest fix: always call `expire` in a `finally`,
  or use `redis_client.set(key, 1, ex=WINDOW, nx=True)` first and `incr`
  only when the key already exists.

### 2. Unhandled DB write in `/detect` hot path → 500 on transient error
- **File:** `backend/app/detection/router.py:79` (the
  `await alert_service.upsert_alert(payload)` call)
- **Problem:** `detect_threats` is called synchronously by application
  middleware on every HTTP request (per its own docstring). A transient DB
  error inside `upsert_alert` (pool exhaustion, dedup_key race) now
  propagates as an unhandled `DatabaseException` → HTTP 500, even though the
  detection result (`result`) was already computed correctly beforehand.
  This also added a synchronous DB round-trip to what was previously a pure
  in-memory computation on a hot path.
- **Fix approach:** Wrap the `upsert_alert` call in try/except, log the
  failure, and still return `result` (the detection outcome must not depend
  on alert-persistence succeeding). Consider moving the alert write to a
  `BackgroundTask` so it never blocks the response at all (see finding #6 —
  fixing both together is efficient since both touch this same call site).

### 3. Model-metrics broadcast: redundant query, no debounce, no error guard
- **File:** `backend/app/features/engine_telemetry/service.py:85-91`
  (calls into `backend/app/features/dashboard/service.py:100-101` →
  `backend/app/features/dashboard/repository.py:174-217`)
- **Problem:** Three issues in the same new code path:
  1. Re-queries `EngineTelemetrySnapshot` from the DB for data that's
     already in memory as `persisted`/`payload` a few lines earlier.
  2. Runs unconditionally on every `ingest()` call, unlike the sibling
     `_broadcast_dashboard_series()` three lines below, which is debounced
     to once per `_DASHBOARD_SERIES_BROADCAST_INTERVAL_SECONDS` (5s)
     specifically because "telemetry can be ingested at a high cadence."
  3. Has no try/except — every other broadcast helper on `DashboardService`
     wraps itself in `try/except Exception: logger.warning(...)`.
     `DashboardRepository.get_model_metrics` actively re-raises DB errors as
     `DatabaseException`, so a DB hiccup here fails the *entire* telemetry
     ingest request.
- **Fix approach:** Derive model metrics from `persisted` in memory instead
  of re-querying; gate the broadcast behind the same debounce window as
  `_broadcast_dashboard_series` (or a dedicated one); wrap the broadcast in
  try/except-and-log matching the rest of `DashboardService`.

### 4. Port filter checked against current page, not full dataset
- **File:** `frontend/src/app/(dashboard)/sessions/page.tsx:60-90`
- **Problem:** This diff added full `source_port`/`destination_port` support
  to the backend (`sessions/{schemas,router,repository}.py`) and to the
  frontend client type (`FetchSessionsParams` in
  `frontend/src/lib/backend/sessions.ts`), and added a `port` search param +
  UI badge to this page — but the actual `fetchSessionsFromBackend(...)`
  call (line ~60) never forwards `source_port`/`destination_port`. The
  `portMatch` filter (line ~90) only runs against the already-paginated
  50-row page (`limit: 50, offset`), unlike `protocol`, which *is* forwarded
  server-side.
- **Fix approach:** Pass `source_port`/`destination_port` through to
  `fetchSessionsFromBackend` from the `port` search param (mirror how
  `protocol` is handled a few lines above), and drop the client-side
  `portMatch` filter once the backend does the filtering.

### 5. Alert `metadata_json` merge uses truthiness, drops intentional `{}`
- **File:** `backend/app/features/alerts/service.py:92`
- **Problem:** `existing.metadata_json = payload.metadata_json or existing.metadata_json`
  uses Python truthiness; `{}` is falsy, so an explicit empty-dict update is
  silently dropped in favor of the stale value. Two lines above, `port` uses
  the correct pattern: `payload.port if payload.port is not None else existing.port`.
  `POST /alerts/upsert` accepts `AlertUpsertRequest` directly from the caller
  with no validation preventing `metadata_json: {}`, so this is reachable
  today, not just latent.
- **Fix approach:** Change to
  `payload.metadata_json if payload.metadata_json is not None else existing.metadata_json`,
  matching the `port` field's pattern.

### 6. `/detect`-created alerts never broadcast to realtime/dashboard subscribers
- **File:** `backend/app/detection/router.py:79` (same call site as #2)
- **Problem:** `IDSEventService.ingest_event` calls
  `_broadcast_realtime_message` / `_broadcast_dashboard_metrics` /
  `_broadcast_dashboard_series` after creating an alert.
  `detect_threats` calls `alert_service.upsert_alert` directly with no
  equivalent broadcast. Alerts from `/detect` are persisted and visible via
  `GET /alerts` on refresh, but never push to the `threat_notifications`
  realtime channel or dashboard live panels — silently invisible in the live
  UI until a manual refresh.
- **Fix approach:** After a successful upsert, call the same
  broadcast helpers `IDSEventService` uses (`RealtimeService.broadcast_alert`
  / `broadcast_logs_update`, `DashboardService.broadcast_summary_metrics`
  etc.), guarded by try/except like the existing call sites, so this
  doesn't reintroduce finding #2 if broadcasting itself fails. Consider
  factoring the "upsert alert + broadcast" sequence into one shared service
  method both `detect_threats` and `IDSEventService` call, which also helps
  finding #8 (misplaced business logic + duplicate dedup-key scheme).

### 7. `modelMetrics` polling removed with no staleness fallback
- **File:** `frontend/src/lib/realtime/use-dashboard-realtime.ts:270-276`
- **Problem:** The diff deletes a `refreshModelMetrics` callback plus a 30s
  `setInterval`/`clearInterval` effect (comment: "modelMetrics has no
  realtime broadcast channel yet"). A new push-only `model_metrics` realtime
  channel was added, but it only fires as a side effect of an engine's
  telemetry ingestion. The remaining `poll()` runs exactly once on mount;
  its `catch` only sets `error`/`loading` state, never retries. With no
  engine connected (fresh deploy, all engines offline, between
  registrations) or a transient failure of that one mount-time poll,
  `modelMetrics` can go stale/null indefinitely — no bounded-staleness
  guarantee remains.
- **Fix approach:** Either restore a periodic fallback poll (longer interval
  is fine now that push exists, e.g. every 60s as a safety net) or add
  retry-with-backoff to the mount-time `poll()` call so a single failure
  isn't permanent.

### 8. Router inlines alert-building logic, duplicates dedup-key scheme
- **File:** `backend/app/detection/router.py:24-31` (`_severity_from_score`)
  and `:45-79` (the rest of `detect_threats`)
- **Problem:** Severity classification, SHA-256 dedup-key hashing, and full
  `AlertUpsertRequest` text/metadata assembly are all inlined directly in
  the route handler. `docs/coding-standards.md:28` requires routers stay
  thin and delegate to a service. This also duplicates dedup-key logic that
  already exists with a *different* format in
  `backend/app/features/ids_events/service.py:194-198`
  (`IDSEventService._build_dedup_key`, session/src-based string vs. this
  router's `"http_detection:" + sha256(...)`). Two independently-maintained
  dedup-key schemes now exist in the codebase.
- **Fix approach:** Extract `_severity_from_score` and the alert-building
  block into a service method (e.g. on `AlertService` or a new
  `DetectionOrchestrator` method), following the router → service → repo
  layering used elsewhere. While there, decide on one dedup-key
  scheme/format and have both `detect_threats` and `IDSEventService` call
  it — don't just relocate the duplicate.

### 9. New migration filename isn't timestamp-prefixed
- **File:** `backend/migrations/versions/f7a91c3e5d02_add_alert_detection_fields.py`
- **Problem:** `docs/coding-standards.md:35` says new migrations should
  prefer `YYYYMMDD_NNN_description.py`; 12 of 16 files in
  `migrations/versions/` already follow it. This new file uses the
  deprecated bare Alembic-hash style.
- **Fix approach:** Rename to something like
  `20260722_001_add_alert_detection_fields.py` (confirm the next free `NNN`
  for that date against existing files) and update the `down_revision`
  chain (check what currently points to `f7a91c3e5d02` as its `down_revision`
  and update it to the new revision id/filename — Alembic revision IDs
  inside the file, not just the filename, need to stay consistent; safest
  is to regenerate via `alembic revision` conventions rather than a plain
  `mv`).

### 10. `middleware.ts` matcher list duplicates dashboard route directories
- **File:** `frontend/src/middleware.ts:11-23`
- **Problem:** `config.matcher` hardcodes 11 paths by hand, byte-for-byte
  duplicating the directory list under `src/app/(dashboard)/`. Forgetting to
  add a new page to this array means `x-pathname`/`x-search` never get set
  for it, so `sanitizeNextPath` returns null and the user is silently
  bounced to bare `/login` with no `next=` — a UX regression with no error
  to signal it.
- **Fix approach:** Replace the explicit list with a negative-lookahead
  matcher (Next.js convention), e.g.
  `"/((?!api|_next|login|signup|favicon.ico).*)"`, so new dashboard pages
  are covered automatically. Confirm this doesn't also match routes that
  should be excluded (public marketing pages, if any exist outside
  `(dashboard)/`).

---

## Suggested working order

1-2-6 touch the same file/call site (`detection/router.py`) and are related
(fix #2's try/except, then add #6's broadcast inside it, informed by #8's
refactor into a service) — do these together as one pass over
`detection/router.py`, ending with the router calling one clean service
method.

3 and 7 are both realtime/telemetry staleness-and-safety issues — can be
done together in one pass over the telemetry/realtime broadcast code.

4, 5 are independent, quick, isolated bugs — good warm-up fixes.

9, 10 are convention/cleanup, lowest risk, no rush.

## Verification checklist per fix

- Backend: `cd backend && python -m unittest discover tests` (repo uses
  `unittest`, not `pytest`, despite `pytest.ini` existing — see
  `docs/coding-standards.md`).
- Frontend: `cd frontend && bun run lint` and `npx tsc --noEmit`.
- For #1, #3: manually exercise the Redis failure path if feasible, or at
  least confirm the new code path via a unit test with a mocked Redis client
  raising on `expire`.
- For #4: confirm a session outside the first 50 rows is now reachable via a
  port filter (seed >50 sessions, filter a port on a session beyond page 1).
- For #9: run `alembic history` (or equivalent) after renaming to confirm
  the revision chain still resolves head-to-base with no gaps.
