# SmartIDS: Browser-Based Engine Registration + Capture-Level Watch/Exclude Filtering

**Status**: Part B implemented 2026-07-19 (see `docs/roadmap.md` Completed section). Part A (engine registration) still planned, not yet implemented. Persisted here (repo-tracked) rather than only in the ephemeral `~/.claude/plans/` slot, so it survives across sessions and future unrelated `/plan` invocations. See `docs/roadmap.md` for the one-line pointer entries.

## Context

Two independent features, planned together in one pass:

**A. Browser-based engine registration.** Today every engine instance authenticates to the backend with one global shared secret (`SMARTIDS_INTERNAL_SERVICE_TOKEN`, HMAC-signed per request — see `docs/decisions.md`). That's fine for a single trusted deployment, but doesn't support "a user runs SmartIDS on N machines and manages them from one dashboard, each individually revocable." The user supplied a design doc (device-linking style: engine opens a local server + browser, user approves in the dashboard, backend issues a per-engine credential). This plan adapts that doc to this codebase's actual patterns (API keys' credential-hashing model, the existing HMAC/nonce auth machinery, the existing engine WS client/command channel).

**Confirmed scope decisions (from user, do not re-litigate):**
- **No per-engine data scoping.** `ids_events`/`alerts`/`sessions`/`engine_telemetry` stay in the single global pool, untouched. The `engines` table is a registration/credential/status management layer only — it does not attempt real per-tenant data isolation. Consequence (flagged honestly below, not hidden): a "packets/threats seen by this specific engine" dashboard column isn't achievable without a later migration adding `engine_id` to those tables — Phase 2 below explicitly defers those two columns rather than faking them.
- **Coexist, don't replace.** The existing global-token path keeps working unchanged (matches the doc's "engine functions independently of backend when offline" / "registration required only for cloud features" goals). Per-engine credentials are an additive second auth path.
- **All 3 phases planned in detail** (per user request), including the Phase 3 items that build on Phase 1/2 pieces — those sub-designs are flagged where they're a firm plan vs. a sketched extension point, since some (credential rotation grace window, revoked-engine live disconnect, disk-backed local buffering) are genuinely bigger and shouldn't be over-specified against code that doesn't exist yet.

**B. Capture-level IP/port watch & exclude filtering**, to "streamline the packet catcher" (reduce load by not processing traffic that isn't interesting). Confirmed via direct read: `packet_capture/sniffers/live_sniffer.py:31-36` already passes `filter=self.packet_filter` straight into `scapy.sniff()`, which compiles it as a BPF program applied by libpcap **before** packets ever reach Python (`packet_capture/utils/packet_filters.py` already has `basic_filter()`→`"ip"`, `web_traffic_filter()`, etc., but no allow/exclude-list builder). This means the feature is almost entirely a filter-string builder plus wiring — no queue/session/feature/ML code needs to change, and filtered-out packets cost zero queue slots or CPU, which is the actual "streamline" win.

---

## Part A: Browser-Based Engine Registration

### Trust model note (read first — affects the data model)

HMAC request signing requires the **raw** shared secret as the HMAC key, both to sign (engine) and verify (backend recomputes the HMAC and compares). This is different from how `api_keys` stores credentials (`backend/app/features/api_keys/key_utils.py` — one-way `hash_api_secret`, verified via `hmac.compare_digest` against a *presented* value): API keys never need the raw secret again after issuance, but the internal-auth signing scheme does, every single request. So the new `engines` table stores the per-engine secret **in plaintext** (same trust level as today's `SMARTIDS_INTERNAL_SERVICE_TOKEN` env var — protected by DB access control, not by hashing). This is a deliberate, stated trade-off, not an oversight: switching to a "present the bearer secret, backend rehashes and compares" model instead (like API keys) would be simpler but would drop the per-request signature/replay protection the current scheme gives every other internal caller, and the user asked for coexistence with that scheme, not a downgrade of it.

### Phase 1 — Independent startup, browser registration, credential issuance, persistent local config

**Backend data model** — new `app/features/engines/models.py`, following `api_keys/models.py`'s exact conventions (`(CUIDMixin, TimestampMixin, Base)`, `app/db/base.py`):

```python
class Engine(CUIDMixin, TimestampMixin, Base):
    __tablename__ = "engines"
    user_id: str            # FK -> users.id, ondelete CASCADE, indexed
    name: str                # user-chosen label, editable
    engine_public_id: str    # unique, indexed — sent in x-smartids-engine-id header
    secret: str              # plaintext, see trust-model note above
    hostname: str | None
    operating_system: str | None
    version: str | None
    status: Enum("active", "revoked")
    last_seen: datetime | None
    ip_address: str | None
    heartbeat_interval_seconds: int  # default e.g. 30
    revoked_at: datetime | None
    # index (user_id, status) for the dashboard list query
```
New Alembic migration, following `2a839dcadf78_create_api_keys_table.py`'s autogenerated `create_table`+explicit index pattern.

**Registration protocol** (mirrors `verification_tokens.py`/`reset_tokens.py`'s "no DB row for the pending/ephemeral part, Redis-backed TTL" pattern — only the *approved* engine gets a permanent row):

1. Engine generates `registration_id = secrets.token_urlsafe(24)`, starts a temporary local HTTP server on an OS-assigned port, and calls `POST {backend_url}/api/v1/engines/register/init` with `{registration_id, hostname, os_name, version}` — **unauthenticated** (no credential exists yet). Backend stores this as a JSON blob in Redis, key `engine-registration:pending:<registration_id>`, TTL 600s.
2. Engine opens the user's browser via stdlib `webbrowser.open(...)` to `{frontend_url}/engines/register?registration_id=<id>&callback_port=<port>`.
3. Frontend page is inside the existing `(dashboard)` route group, so it's already session-gated by `(dashboard)/layout.tsx`'s redirect-to-`/login` — **but that redirect currently has no "return here after login" mechanism** (confirmed: no `next=`/`callbackUrl` param anywhere in login/OAuth code today). This is a small, required prerequisite change: parameterize the redirect target — `layout.tsx` appends `?next=<currentPath+query>` to the `/login` redirect; the login server action reads `next` and redirects there instead of the hardcoded `/overview` on success; the OAuth callback route roundtrips `next` through the existing `state` parameter the same way. Contained change, same shape in both call sites.
4. Page calls `GET /api/v1/engines/register/{registration_id}` (session-authenticated) — returns the pending hostname/os/version for display, 404/410 if expired or already consumed.
5. User names the engine and clicks Approve → `POST /api/v1/engines/register/{registration_id}/approve` `{name}` (session-authenticated) — backend creates the `Engine` row (`user_id` = current user, generates `engine_public_id` + `secrets.token_urlsafe(48)` secret), deletes the Redis pending key, returns `{engine_id, engine_secret, backend_url, heartbeat_interval}` **once**.
6. Frontend relays this straight to the waiting engine: `fetch("http://127.0.0.1:{callback_port}/complete", {...})` — a same-machine loopback call (same trust pattern as `gh auth login`/Docker Desktop device-linking). The temp server must serve a same-origin-permissive `OPTIONS`/CORS response since the calling page's origin is the dashboard, not localhost.
7. Engine's temp server validates the posted `registration_id` matches the one it generated (per the doc's "do not trust localhost requests alone" — this check is what prevents an unrelated local process from completing a registration it didn't start), writes the local config file, shuts itself down, and normal startup continues. Timeout: if `/complete` never arrives within ~10 minutes, the temp server shuts down and the engine proceeds in unregistered/global-token (or unauthenticated local) mode — **packet capture itself is never gated on this**, matching the doc's "packet analysis must never depend on backend availability."

**Local config** — new small module (`packet_capture/registration/local_config.py`), following `response_engine/processed_command_store.py`'s exact atomic-write pattern (write `<path>.tmp`, `Path.replace()`, `threading.Lock`, tolerant-of-missing/corrupt-file load): stores `{engine_id, engine_secret, backend_url, heartbeat_interval}` as one JSON object, path overridable via `SMARTIDS_ENGINE_CONFIG_PATH` (default e.g. `./engine_config.json`).

**Engine-side new modules** (`packet_capture/registration/`):
- `registration_server.py` — stdlib `http.server`/`socketserver` (no new dependency — confirmed nothing like this exists yet and stdlib suffices), one route `POST /complete`, self-shutting.
- `registration_client.py` — does step 1/2 above (`POST .../register/init`, `webbrowser.open`), then blocks (with timeout) for the local server to receive `/complete`.

**`SnifferService.__init__` startup branch** (`packet_capture/sniffer_service.py`, where `internal_request_signer`/env vars are read today, lines ~30-45):
- If a local engine config file exists → load it, build `InternalRequestSigner(engine_secret)`, and every forwarder/poller/WS-client attaches `x-smartids-engine-id: <engine_id>` alongside the existing signature headers.
- Else if `SMARTIDS_INTERNAL_SERVICE_TOKEN` is set → today's global-token path, unchanged (coexistence).
- Else if neither is set and a new `SMARTIDS_ENGINE_REGISTRATION_ENABLED=true` flag is set → kick off the registration flow (steps 1-7) before/alongside normal startup — additive and opt-in, matching every other engine integration's existing convention.

**Backend auth extension** (`backend/app/common/internal_auth.py`, `require_internal_service_auth`): add an optional `x-smartids-engine-id` header check *before* falling back to the global-token path — if present, look up the `Engine` row by `engine_public_id`, reject if missing/revoked, use `engine.secret` as the HMAC key instead of `settings.SMARTIDS_INTERNAL_SERVICE_TOKEN` for the rest of the existing `verify_internal_signature`/nonce-replay flow (that machinery itself — signature+timestamp+nonce — is unchanged, it's engine-agnostic per the earlier exploration). Same treatment for the WS handshake: `EngineWSAuthPayload` (`app/features/realtime/engine_ws_schemas.py`) gains an optional `engine_id` field; `_authenticate()` (`engine_ws_router.py`) resolves the secret the same way.

**Backend routes** (`app/features/engines/router.py`, following `api_keys/router.py`'s layering exactly):
- `POST /engines/register/init` — unauthenticated, writes the Redis pending entry.
- `GET /engines/register/{registration_id}` — session-authenticated, reads pending entry.
- `POST /engines/register/{registration_id}/approve` — session-authenticated, creates the `Engine` row, returns the credential once.
- `GET /engines` — session-authenticated, owner-scoped, paginated list (mirrors `api_keys` list route).
- `PATCH /engines/{id}` — rename only, owner-scoped.
- `DELETE /engines/{id}` — soft revoke (`status="revoked"`, `revoked_at=now()`), owner-scoped, row kept for audit.

**Frontend**:
- `frontend/src/app/(dashboard)/engines/page.tsx` + `EnginesManager` component — cloned structurally from `api-keys-manager.tsx` (same Table/Dialog/AlertDialog/Badge shadcn primitives, same TanStack Query + server-action pattern, `frontend/src/lib/actions/engines.ts` + `frontend/src/lib/backend/engines.ts` mirroring `api-keys.ts`'s `requestBackendJson`/`unwrapBackendData` wrapper).
- `frontend/src/app/(dashboard)/engines/register/page.tsx` — the approval landing page (steps 3-6 above): reads `registration_id`/`callback_port` from search params, shows pending metadata, Approve/Deny buttons, relays the issued credential to `localhost:{callback_port}/complete` client-side.
- Login `next=` redirect-preservation change described above.

### Phase 2 — Heartbeats, WS connectivity, dashboard status

- **Heartbeat reuses existing infra rather than adding a new endpoint/loop**: the engine's already-periodic telemetry push (`packet_capture/telemetry/engine_telemetry.py` → `fastapi_engine_telemetry_forwarder.py`, already running on `SMARTIDS_ENGINE_TELEMETRY_INTERVAL_SECONDS`) is extended so that, when the request carries `x-smartids-engine-id`, the backend's `engine_telemetry` service also upserts `Engine.last_seen`/`ip_address`/`status="active"`. No new periodic loop, no new endpoint — reuse over new abstraction.
- **WS connectivity status**: `engine_ws_router.py`'s connect/disconnect handlers, once `engine_id` is known from the auth payload (Phase 1's extension), update the same `last_seen`/status fields on connect and mark disconnected on close.
- **Dashboard**: `EnginesManager` (Phase 1) gains a live status badge, fed by a new `"engine_status"` realtime channel added to the closed union in `frontend/src/lib/realtime/use-realtime-channel.ts`, broadcast from the backend on heartbeat/connect/disconnect (mirrors the existing `_broadcast_realtime_message` pattern used elsewhere in `realtime/service.py`). **Packet-rate and threat-count columns from the original doc are explicitly deferred** — per the "no per-engine data scoping" decision, `ids_events`/`alerts` carry no `engine_id`, so those numbers can't be computed per-engine without the migration this plan is deliberately not doing; showing them anyway would be misleading for multi-engine users. Ship status/version/last-seen only; revisit if per-engine data scoping is approved later.

### Phase 3 — Remote policy, rule sync, rotation, revocation, reconnection, local buffering

- **Remote policy/config push**: reuse the already-built engine command WS channel (`EngineWSClient`/`engine_ws_router.py`, from the earlier engine-improvement plan) rather than inventing a new transport — add a new envelope `type: "config_update"` alongside the existing `"command"` type. This is also the natural delivery mechanism for Part B's watch/exclude filter list if it's ever made dashboard-editable (noted as a future extension point, not built now since it wasn't requested).
- **Credential rotation**: `POST /engines/{id}/rotate` (session-authenticated, owner-scoped) generates a new secret; to avoid instantly locking out an already-connected engine mid-session, the `Engine` row keeps a short-lived `previous_secret`/`previous_secret_expires_at` pair so either secret verifies during the grace window. The engine receives the new secret over the same WS channel (`type: "credential_rotated"`) and atomically rewrites its local config file.
- **Revocation, made live**: Phase 1's `DELETE /engines/{id}` already stops new auth from succeeding, but an *already-open* WS connection for a revoked engine should be force-closed rather than left running until its next reconnect. This needs a small registry the WS router doesn't currently have — today's `engine_ws_router.py` was built for a single global engine, not a many-engines-per-user registry (`engine_id -> active WebSocket`). Flagged as a genuinely new piece of state, not a copy of an existing pattern — worth its own short design pass when this phase is actually picked up, rather than speced line-by-line here.
- **Auto-reconnect**: already exists (`EngineWSClient`'s exponential-backoff reconnect from the earlier plan) — no new work; the engine's `engine_id`/secret persist across reconnects since they live in the local config file, not in memory.
- **Local event buffering when the backend is unreachable**: today's forwarders (`BackgroundPublisher`) drop-and-log on a full queue rather than durably buffering. Making this disk-backed (spill dropped events to a bounded local file, replay on reconnect) is the most invasive Phase 3 item and is flagged, not fully speced, as its own future sub-design — the concrete extension point is `BackgroundPublisher`'s drop path, which would redirect to a disk-backed spill file instead of discard+log.

### Security notes (from the source doc, confirmed applicable)

- `registration_id` is single-use (Redis key deleted on `/approve`) and TTL-bounded (600s).
- Temp local server binds `127.0.0.1` only, self-times-out (~10 min), and checks the posted `registration_id` matches — the "don't trust localhost alone" mitigation.
- `engine.secret` is plaintext at rest (trust-model note above) — same exposure as today's global token, not a regression.
- Coordinated redeploy is **not** required this time (unlike the earlier HMAC-hardening workstream) — this is purely additive; engines that never register keep working exactly as they do today.

---

## Part B: Capture-level IP/port watch & exclude filtering

**Design**: extend `packet_capture/utils/packet_filters.py` with a builder function, e.g.:

```python
@staticmethod
def build_capture_filter(*, watch_ips=None, watch_ports=None, exclude_ips=None, exclude_ports=None) -> str:
    # base is always "ip" (today's default via basic_filter()); combine with
    # "and (host A or host B or port X ...)" for the allow-list, and
    # "and not (host C or port D ...)" for the block-list; both may combine.
```
Malformed entries (bad IPv4, out-of-range port) are logged and skipped rather than crashing the engine — same safe-parsing convention as the repo's existing `_positive_int` helper.

**Wiring**: new env vars `SMARTIDS_CAPTURE_WATCH_IPS`, `SMARTIDS_CAPTURE_WATCH_PORTS`, `SMARTIDS_CAPTURE_EXCLUDE_IPS`, `SMARTIDS_CAPTURE_EXCLUDE_PORTS` (comma-separated), read in `SnifferService.__init__` alongside `SMARTIDS_CAPTURE_INTERFACE` (`sniffer_service.py:30`), replacing the currently-hardcoded `packet_filter=PacketFilters.basic_filter()` (`sniffer_service.py:33`) with a call to the new builder — defaults to today's exact behavior (`"ip"`) when nothing is configured, so this is purely additive.

**Why this is the whole feature**: `LiveSniffer` already passes `filter=self.packet_filter` straight to `scapy.sniff()` (`live_sniffer.py:31-36`), which libpcap compiles as a BPF program applied **before** packets reach any Python code — confirmed no local code re-implements filtering downstream. So there's no queue, session-builder, feature-extractor, or ML code to touch; unwanted packets never cost a queue slot or a CPU cycle, which is the actual performance win the user is asking for.

---

## Complications / open items surfaced (verify before implementing, not papered over)

1. Frontend's `(dashboard)` layout has no existing `next=`/return-path mechanism — Part A's registration approval page cannot work without adding it first (small, contained, described above, but is a genuine prerequisite, not optional).
2. `engine.secret` plaintext-at-rest is a deliberate trade-off, not an oversight — flagged so it isn't "discovered" mid-implementation and second-guessed without the context above.
3. Phase 2's packet-rate/threat-count columns from the source doc are explicitly not being built as literally specified (per the "no per-engine data scoping" decision) — make sure whoever implements Phase 2 doesn't quietly try to fake these from the global pool.
4. Phase 3's revocation-live-disconnect needs a new `engine_id -> WebSocket` registry that doesn't exist yet (today's WS router assumes one global engine) — this is real new state, not a reuse of an existing pattern.
5. Rate-limiting `POST /engines/register/init` (unauthenticated by necessity) wasn't investigated — no existing rate-limit infra was found anywhere in the backend during exploration; worth an explicit decision (accept as-is / add one) before this ships, not assumed.

## Critical files (Part A)

- `backend/app/features/engines/` — new feature module (models/router/service/repository/schemas), modeled on `app/features/api_keys/`.
- `backend/app/common/internal_auth.py` — extended to resolve a per-engine secret when `x-smartids-engine-id` is present.
- `backend/app/features/realtime/engine_ws_router.py`, `engine_ws_schemas.py` — `engine_id` added to the WS auth payload.
- `packet_capture/sniffer_service.py` — startup branch choosing local-config vs. global-token vs. registration-flow.
- `packet_capture/registration/` — new package (local config, temp server, registration client).
- `frontend/src/app/(dashboard)/engines/`, `frontend/src/app/(dashboard)/layout.tsx`, login action, OAuth callback route.

## Critical files (Part B)

- `packet_capture/utils/packet_filters.py` — new builder function.
- `packet_capture/sniffer_service.py` — env-var reads + wiring at the existing `packet_filter=` construction site.

## Verification

- **Part A**: unit tests for the new HMAC-secret-resolution branch in `internal_auth.py` (per-engine secret accepted, revoked engine rejected, missing header falls back to global token unchanged); integration test for the full register/init → approve → local-config-write loop (can simulate the loopback POST without a real browser); manual end-to-end run — start an unregistered engine locally, confirm it opens a browser to the right URL, approve in the dashboard, confirm the engine picks up the credential and subsequent forwarded requests carry `x-smartids-engine-id` and succeed.
- **Part B**: unit tests for `build_capture_filter` (allow-only, block-only, combined, malformed-entry-skipped cases); manual run — set `SMARTIDS_CAPTURE_EXCLUDE_PORTS=22` (or similar), confirm via a packet capture tool (e.g. `tcpdump`) that SSH traffic never reaches the engine's queue/telemetry counts, while unrelated traffic is unaffected.

## Ultraplan status

Sent to Ultraplan (cloud refinement) on 2026-07-19 — session `session_01ToEC8FPcQWije7mC3vJ25e`. If a refined version comes back, reconcile it into this file rather than keeping two divergent copies.
