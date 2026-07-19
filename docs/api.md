# API Reference

Every backend REST/WebSocket endpoint (`backend/`, FastAPI, submodule `ids-api`), read directly from `backend/app/features/*/router.py`, `schemas.py`, `exceptions.py`, and `backend/app/common/*`. All routes mount under `/api/v1` (`backend/app/main.py`). System context: `docs/architecture.md`. Table detail: `docs/database.md`.

---

## Conventions That Apply to Every Endpoint

**Response envelope** — every success response is built by `create_response()` (`app/common/responses.py`):
```json
{ "success": true, "message": "...", "data": <payload>, "meta": { "timestamp": "<ISO-8601>", "request_id": "<uuid>" } }
```

**Error envelope** — every error response is built by `create_error_response()`, via one of three global handlers (`app/common/exception_handlers.py`, registered in `main.py`):
```json
{ "success": false, "message": "...", "error_code": "...", "details": {...}, "meta": {...} }
```
| Handler | Triggers on | Status | error_code |
|---------|-------------|--------|------------|
| `app_exception_handler` | Any `AppException` subclass (feature exceptions below) | `exc.status_code` | `exc.error_code` |
| `validation_exception_handler` | FastAPI/Pydantic request validation failure (bad body/query types, failed field constraints) | 422 | `VALIDATION_ERROR`, `details` = `{"<field path>": "<message>"}` |
| `unhandled_exception_handler` | Any other uncaught exception | 500 | `INTERNAL_ERROR` (message/details hidden; full trace logged server-side) |

In production (`settings.is_production`), `AppException` responses with `status_code >= 500` hide `message`/`details` (generic "An unexpected error occurred" instead). Below, this shared 422/500 behavior is **not** repeated per endpoint — only feature-specific exceptions and any endpoint-specific deviation are listed.

**Request body casing** — only `auth` and `user_sessions` schemas inherit `CamelModel` (`app/common/schemas.py`: `alias_generator=to_camel`, `populate_by_name=True`), so those two features accept/emit **camelCase** JSON keys (e.g. `fullName`, `newPassword`) while still allowing snake_case via `populate_by_name`. Every other feature's schemas are plain `BaseModel` with **snake_case** keys only — there is no camelCase alias for `ids_events`, `alerts`, `sessions`, `threats`, `engine_commands`, `engine_telemetry`, `block_events`, `blocked_ips`, `sql_injection`, `realtime`, `dashboard`, or `api_keys`... except `api_keys` schemas *also* inherit `CamelModel` (confirmed in its `schemas.py`). This is an inconsistency across the API surface, not a documentation simplification — verify casing per endpoint below before integrating a client.

**Auth mechanisms**:
- **Session** — `get_current_user`/`get_current_auth_session` (`app/features/auth/dependencies.py`). Token read from the `session_token` cookie (`SESSION_COOKIE_NAME`) **or** an `Authorization: Bearer <token>` header, whichever is present (cookie checked first). Raises `UnauthorizedException` (401, `UNAUTHORIZED`) if no token found or the session lookup fails.
- **Internal service** — `require_internal_service_auth` (`app/common/internal_auth.py`). Compares the `x-smartids-internal-token` request header to `settings.INTERNAL_SERVICE_TOKEN`. **If `INTERNAL_SERVICE_TOKEN` is empty/unset, the check silently passes with no auth enforced at all** — this is opt-in-by-config, not fail-closed. Raises `UnauthorizedException` (401, `UNAUTHORIZED`) on mismatch when a token is configured.
- **None** — no dependency of either kind on the route.

---

## Auth (`/api/v1/auth`) — `app/features/auth/`

Schemas use `CamelModel` (camelCase JSON).

### `POST /auth/register`
- **Auth**: None (public).
- **Request body** (`RegisterRequest`): `fullName: str`, `email: EmailStr`, `password: str` (8–128 chars).
- **Parameters**: none.
- **Response** `201`: `{ "user": UserResponse }` — `UserResponse`: `id, email, emailVerified (datetime|null), isActive, createdAt, updatedAt`.
- **Error responses**: `409 EMAIL_ALREADY_EXISTS` (`EmailAlreadyExistsException`) if the email is already registered.
- **Internal flow**: `router.register` → `AuthService.register()` (reads `request.headers["user-agent"]` and `get_client_ip(request)` — in `ENVIRONMENT=development`, a loopback client IP is replaced with a **randomized fake public IP** for testing, `app/common/utils.py::get_client_ip`) → hashes password with **argon2** → inserts `users` row → returns user (no session cookie set on register).

### `POST /auth/login`
- **Auth**: None (public; this *creates* the session).
- **Request body** (`LoginRequest`): `email: EmailStr`, `password: str`.
- **Response** `200`: `{ "user": UserResponse }`; sets `session_token` HttpOnly cookie (`Secure`=`SESSION_COOKIE_SECURE`, `SameSite`=`SESSION_COOKIE_SAMESITE`, `Max-Age`=`SESSION_TTL_SECONDS`=604800 default).
- **Error responses**: `401 INVALID_CREDENTIALS` (`InvalidCredentialsException`) on bad email/password; `401 EMAIL_NOT_VERIFIED` (`EmailNotVerifiedException`) if the account's email isn't verified yet.
- **Internal flow**: `AuthService.login()` → verify argon2 hash → create `sessions` row (`token_hash`, `expires_at`, `user_agent`, `ip_address`) → return raw token to router → `set_session_cookie()`.

### `POST /auth/logout`
- **Auth**: Session token read manually from cookie or Bearer header (not via the `get_current_user` dependency — logout doesn't 401 if no token is present, it just no-ops the revoke step).
- **Request body**: none.
- **Response** `200`: `{}`; clears the session cookie unconditionally.
- **Error responses**: none feature-specific (silently succeeds even with no/invalid token).
- **Internal flow**: if a token was found, `AuthService.logout(raw_token)` revokes the matching `sessions` row (`revoked_at`); cookie cleared regardless.

### `GET /auth/me`
- **Auth**: Session (`get_current_user`).
- **Response** `200`: `{ "user": UserResponse }`.
- **Error responses**: `401 UNAUTHORIZED` if not authenticated.

### `POST /auth/verify-email`
- **Auth**: None.
- **Request body** (`VerifyEmailRequest`): `token: str`.
- **Response** `200`: `{ "user": UserResponse }`; sets a new session cookie (auto-login on verification).
- **Error responses**: `400 EMAIL_VERIFICATION_FAILED` (`EmailVerificationException`) if the token is invalid/expired.
- **Internal flow**: `AuthService.verify_email(token)` validates the signed token (`verification_tokens.py`), sets `users.email_verified`, creates a session, returns it.

### `POST /auth/verify-email/resend`
- **Auth**: None.
- **Request body** (`ResendVerificationRequest`): `email: EmailStr`.
- **Response** `202`: `{}`, fixed message `"If an unverified account exists, a verification email has been sent"` — **deliberately identical regardless of whether the account/verification state exists**, to prevent email enumeration.
- **Error responses**: none surfaced to the client (enumeration-safe by design).

### `POST /auth/forgot-password`
- **Auth**: None.
- **Request body** (`ForgotPasswordRequest`): `email: EmailStr`.
- **Response** `202`: `{}`, same enumeration-safe fixed message regardless of whether the account exists (explicit in the router docstring).
- **Error responses**: none surfaced.

### `POST /auth/reset-password`
- **Auth**: None (bearer is the reset token itself, not a session).
- **Request body** (`ResetPasswordRequest`): `token: str`, `newPassword: str` (8–128 chars).
- **Response** `200`: `{}`.
- **Error responses**: `400 PASSWORD_RESET_FAILED` (`PasswordResetException`) if the token is invalid/expired/already used.
- **Internal flow**: on success, invalidates the reset token and **revokes all active sessions** for the user (router docstring: "all active sessions are revoked").

### `GET /auth/oauth/{provider_name}/start`
- **Auth**: None.
- **Parameters**: path `provider_name: str` (currently only `github` is configured).
- **Response**: `302` redirect to the provider's authorization URL (not a JSON envelope).
- **Error responses**: `503 OAUTH_PROVIDER_NOT_CONFIGURED` (`OAuthProviderNotConfiguredException`) if `provider_name` isn't configured (e.g. missing `GITHUB_CLIENT_ID`).
- **Internal flow**: `AuthService.build_oauth_authorization_url(provider_name)` generates state (TTL `OAUTH_STATE_TTL_SECONDS`, default 600s) and the provider's auth URL (Authlib).

### `GET /auth/oauth/{provider_name}/callback`
- **Auth**: None.
- **Parameters**: path `provider_name: str`; query `code: str` (required), `state: str` (required).
- **Response** `200`: `{ "user": UserResponse }`; sets session cookie.
- **Error responses**: `401 OAUTH_AUTHENTICATION_FAILED` (`OAuthAuthenticationException`) if the provider exchange/state validation fails; `503 OAUTH_PROVIDER_NOT_CONFIGURED` if misconfigured.
- **Internal flow**: exchanges `code` for the provider identity, upserts an `oauth_accounts` row (unique on `provider`+`provider_user_id`), creates or reuses the linked `user`, creates a session.

---

## User Sessions (`/api/v1/auth/sessions`) — `app/features/user_sessions/`

Schemas use `CamelModel`.

### `GET /auth/sessions`
- **Auth**: Session (`get_current_user` + `get_current_auth_session`).
- **Parameters** (query): `limit: int` (1–100, default 20), `cursor: str | None` (opaque pagination cursor), `sort: str | None` (`asc`/`desc` on `created_at`, default `desc`).
- **Response** `200`: `CursorPaginatedUserSessionsResponse` — `items: UserSessionResponse[]` (`sessionId, deviceName, deviceType, browser, browserVersion, operatingSystem, location {city,state,country}|null, createdAt, lastActivity, isCurrentSession`), `nextCursor: str|null`, `hasMore: bool`, `limit`.
- **Error responses**: none feature-specific beyond global 401/422.

### `DELETE /auth/sessions/others`
- **Auth**: Session.
- **Response** `200`: `RevokeSessionsResponse` — `{ "revokedCount": int }`. Does not touch the current session/cookie.

### `DELETE /auth/sessions`
- **Auth**: Session.
- **Response** `200`: `RevokeSessionsResponse`; **also clears the caller's own session cookie** (revokes everything including current).

### `DELETE /auth/sessions/{session_id}`
- **Auth**: Session.
- **Parameters** (path): `session_id: str`.
- **Response** `200`: `RevokeSessionsResponse`; clears the session cookie only if the revoked `session_id` matches the caller's current session.
- **Error responses**: `404 SESSION_NOT_FOUND` (`UserSessionNotFoundException`) if the session doesn't exist or isn't owned by the caller.

---

## API Keys (`/api/v1/api-keys`) — `app/features/api_keys/`

Schemas use `CamelModel`. All routes: Auth = Session.

### `POST /api-keys`
- **Request body** (`CreateAPIKeyRequest`): `name: str` (1–255), `description: str|null` (≤1000), `environment: "live"|"test"|"development"` (default `live`), `version: "v1"|"v2"` (default `v1`).
- **Response** `201` (`APIKeyCreatedResponse`): `id, name, description, environment, version, apiKey (full secret, shown once), isActive, createdAt, updatedAt`.
- **Error responses**: `422 API_KEY_LIMIT_EXCEEDED` (`APIKeyLimitExceededException`) if the user's key count is at the configured max.
- **Internal flow**: `APIKeyService.create_api_key()` generates the raw key + `key_id` (public) + one-way `key_hash`; only the raw key is ever returned, and only in this response.

### `GET /api-keys`
- **Parameters** (query): `limit` (1–50, default 10), `offset` (≥0, default 0), `search: str|null` (≤255, case-insensitive over name/description), `environment: str|null`, `isActive: bool|null`.
- **Response** `200`: `PaginatedAPIKeysResponse` — `items: APIKeyResponse[]` (never includes the secret), `totalCount, limit, offset`.

### `GET /api-keys/{api_key_id}`
- **Parameters** (path): `api_key_id: str`.
- **Response** `200`: `APIKeyResponse`.
- **Error responses**: `404 API_KEY_NOT_FOUND` (`APIKeyNotFoundException`).

### `PATCH /api-keys/{api_key_id}`
- **Request body** (`UpdateAPIKeyRequest`): `name: str|null`, `description: str|null`, `isActive: bool|null` — all optional, partial update. The key value itself is never editable (router docstring, enforced by omission from the schema).
- **Response** `200`: `APIKeyResponse`.
- **Error responses**: `404 API_KEY_NOT_FOUND`.

### `DELETE /api-keys/{api_key_id}`
- **Response** `200`: `{}`.
- **Error responses**: `404 API_KEY_NOT_FOUND`.

---

## IDS Events (`/api/v1/ids-events`) — `app/features/ids_events/`

Plain `BaseModel` (snake_case).

### `GET /ids-events`
- **Auth**: Session.
- **Parameters** (query, all optional except pagination): `limit` (1–100, default 20), `offset` (≥0, default 0), `source`, `severity`, `prediction`, `action`, `source_ip`, `destination_ip`, `protocol` (0–255), `session_id`, `start_ts`, `end_ts` (datetimes).
- **Response** `200`: `PaginatedIDSEventsResponse` — `items: IDSEventResponse[]`, `total_count, limit, offset`. `IDSEventResponse` fields: `id, event_id, schema_version, ts, source, model, prediction, confidence, severity, action, protocol, source_ip, destination_ip, source_port, destination_port, attack_type, session_id, features (dict), created_at, updated_at`.

### `POST /ids-events`
- **Auth**: Internal service.
- **Request body** (`IDSEventIngestRequest`, `extra="allow"` — unknown fields accepted and ignored by the schema, not rejected): `schema_version, event_id, ts, source, model, prediction, confidence (0–1), severity, action`, plus optional `protocol, features (dict, default {}), threat_id, source_ip, destination_ip, source_port, destination_port, attack_type, confidence_score, detection_method, action_taken, session_id, risk_score`.
- A **model_validator** back-fills omitted optional fields from required ones if not supplied: `threat_id ← event_id`, `source_ip ← source`, `attack_type ← prediction`, `confidence_score ← confidence`, `detection_method ← "ml"`, `action_taken ← action`, `risk_score ← confidence`.
- **Response**: `201` if newly created / `200` if the `event_id` already existed (idempotent) — body `{ "created": bool, "alert_triggered": bool, "event": IDSEventResponse }`.
- **Error responses**: `422 VALIDATION_ERROR` (global) for schema violations; `422 INVALID_IDS_EVENT_PAYLOAD` (`InvalidIDSEventPayloadException`) for service-level payload issues.
- **Internal flow**: `IDSEventService.ingest_event()` persists (or returns existing) `ids_events` row, and internally decides whether the event also creates/updates an `alerts` row (`alert_triggered`).

---

## Alerts (`/api/v1/alerts`) — `app/features/alerts/`

Plain `BaseModel`.

### `GET /alerts`
- **Auth**: Session.
- **Parameters** (query): `limit` (1–100, default 20), `offset` (≥0), `source_ip, destination_ip, prediction, severity`, `status` (query param name is literally `status`, aliased to `status_value` in the handler), `action`, `start_ts, end_ts`.
- **Response** `200`: `PaginatedAlertsResponse` — `items: AlertResponse[]` (`id, dedup_key, event_id, prediction, severity, confidence, action, source, status, first_seen_at, last_seen_at, occurrence_count, threat_id, detection_method, action_taken, session_id, source_ip, destination_ip, source_port, destination_port, protocol, risk_score, is_final, created_at, updated_at`), `total_count, limit, offset`.

### `POST /alerts/upsert`
- **Auth**: Internal service.
- **Request body** (`AlertUpsertRequest`): `dedup_key, event_id, prediction, severity, confidence (0–1), action, source`, `status` (default `"open"`), plus optional `threat_id, detection_method, action_taken, session_id, source_ip, destination_ip, source_port, destination_port, protocol, risk_score, is_final (default false)`.
- **Response**: `201` if a new alert was created (new `dedup_key`) / `200` if an existing one was updated — body `{ "created": bool, "alert": AlertResponse }`.
- **Error responses**: global 422/500 only (no feature-specific exceptions defined beyond `AlertNotFoundException`, which isn't wired to this route).

---

## Threat Reports (`/api/v1/threats`) — `app/features/threats/`

Plain `BaseModel`. **No dedicated table** — reads/writes the `alerts` table (see `docs/database.md`).

### `GET /threats`
- **Auth**: Session.
- **Parameters** (query): `limit` (1–100, default 20), `offset`, `source_ip, destination_ip, attack_type, severity, status, start_ts, end_ts`.
- **Response** `200`: `PaginatedThreatsResponse` — `items: ThreatResponse[]` (`threat_id, timestamp, source_ip, source_port, destination_ip, destination_port, protocol, attack_type, severity, confidence_score, detection_method, action_taken, status, session_id`), `total_count, limit, offset`. `ThreatResponse` is built from an `Alert` row in `_to_threat_response()`: `threat_id = alert.threat_id or alert.id`, `attack_type = alert.prediction`, `confidence_score = alert.confidence`, `action_taken = alert.action_taken or alert.action`.

### `GET /threats/{threat_id}`
- **Parameters** (path): `threat_id: str` — matched against **either** `Alert.threat_id` **or** `Alert.id` (`ThreatRepository.get_by_threat_id`).
- **Response** `200`: `ThreatResponse`.
- **Error responses**: `404 THREAT_NOT_FOUND` (`ThreatNotFoundException`).

### `POST /threats/{threat_id}/respond`
- **Request body** (`ThreatResponseActionRequest`): `action_taken: str`, `status: str|null`.
- **Response** `200`: `ThreatResponseActionResult` — `{ threat_id, action_taken, status }`.
- **Error responses**: `404 THREAT_NOT_FOUND`.
- **Internal flow**: `ThreatService.apply_response_action()` updates the underlying `Alert` row's `action_taken`/`status`.

---

## Network Sessions (`/api/v1/sessions`) — `app/features/sessions/`

Plain `BaseModel`.

### `GET /sessions`
- **Auth**: Session.
- **Parameters** (query): `limit` (1–100, default 20), `offset`, `source_ip, destination_ip, protocol (0–255), state, min_risk_score (0–1), session_id, start_ts, end_ts`.
- **Response** `200`: `PaginatedNetworkSessionsResponse` — `items: NetworkSessionResponse[]` (`id, session_id, start_time, end_time, last_seen_at, source_ip, destination_ip, source_port, destination_port, protocol, packet_count, byte_count, duration, risk_score, ml_prediction, heuristic_result, state, created_at, updated_at`), `total_count, limit, offset`.

### `GET /sessions/{session_id}`
- **Parameters** (path): `session_id: str` (the engine-assigned `session_id`, not the DB `id`).
- **Response** `200`: `NetworkSessionResponse`.
- **Error responses**: `404 NETWORK_SESSION_NOT_FOUND` (`NetworkSessionNotFoundException`) — raised explicitly in the router (`if not network_session: raise ...`), not just from the service layer.

### `POST /sessions/upsert`
- **Auth**: Internal service.
- **Request body** (`NetworkSessionUpsertRequest`): `session_id, start_time, source_ip, destination_ip, protocol (0–255)` required; `end_time, last_seen_at, source_port, destination_port, packet_count (default 0), byte_count (default 0), duration (default 0.0), risk_score (default 0.0, 0–1), ml_prediction, heuristic_result, state (default "active")` optional.
- **Response**: `201` created / `200` updated (upsert keyed on `session_id`) — `{ "created": bool, "session": NetworkSessionResponse }`.

### `POST /sessions/{session_id}/respond`
- **Auth**: Session.
- **Request body** (`NetworkSessionResponseActionRequest`): `action_taken: str`, `state: str|null`.
- **Response** `200`: `NetworkSessionResponseActionResult` — `{ session_id, action_taken, state }`.

---

## Traffic (`/api/v1/traffic`) — `app/features/traffic/`

Thin read-only wrapper over the **same** `NetworkSessionService`/schemas as `sessions` (imports directly from `app.features.sessions.*`) — not a separate table or service.

### `GET /traffic`
- **Auth**: Session.
- **Parameters**: identical query set to `GET /sessions` (`limit, offset, source_ip, destination_ip, protocol, state, min_risk_score, session_id, start_ts, end_ts`).
- **Response** `200`: `PaginatedNetworkSessionsResponse`, message `"Traffic retrieved"` (data shape identical to `/sessions`).

---

## Logs (`/api/v1/logs`) — `app/features/logs/`

Thin read-only wrapper over `IDSEventService`/schemas (imports from `app.features.ids_events.*`) — same underlying `ids_events` table as `/ids-events` GET, different filter subset.

### `GET /logs`
- **Auth**: Session.
- **Parameters** (query): `limit` (1–100, default 20), `offset`, `severity, action, prediction, source_ip, destination_ip, protocol (0–255), session_id, start_ts, end_ts`. (No `source` filter here, unlike `/ids-events`.)
- **Response** `200`: `PaginatedIDSEventsResponse`, message `"Logs retrieved"`.

---

## Health (`/api/v1/health`) — `app/features/health/`

Thin read-only wrapper over `EngineTelemetryService`/schemas (`app.features.engine_telemetry.*`).

### `GET /health/runtime`
- **Auth**: Session.
- **Response** `200`: latest `EngineTelemetrySnapshotResponse`, or `data: null` if no snapshot has ever been ingested (no 404 — router returns `None` gracefully).

### `GET /health/runtime/history`
- **Parameters** (query): `limit` (1–240, default 30), `offset` (≥0).
- **Response** `200`: `PaginatedEngineTelemetryHistoryResponse` — `items: EngineTelemetrySnapshotResponse[]`, `total_count, limit, offset`.

---

## Engine Commands (`/api/v1/engine-commands`) — `app/features/engine_commands/`

Plain `BaseModel`. All routes: Auth = Internal service.

### `POST /engine-commands`
- **Request body** (`EngineCommandCreateRequest`, `extra="forbid"` — unknown fields rejected as 422): `command_id: str`, `action: Literal["block","unblock","watchlist","unwatchlist"]`, `ip_address: IPvAnyAddress`, `duration_seconds: int` (1–86400, default 300).
- **Response**: `201` if newly enqueued / `200` if `command_id` already existed (**idempotent duplicate submission** — same command_id returns the prior record rather than erroring) — body `EngineCommandResponse` (`command_id, action, ip_address, duration_seconds, status`).

### `GET /engine-commands`
- **Parameters** (query): `limit` (1–100, default 20).
- **Response** `200`: `EngineCommandPollResponse` — `{ "commands": EngineCommandResponse[] }`.

### `POST /engine-commands/ack`
- **Request body** (`EngineCommandAckRequest`, `extra="forbid"`): `command_id: str`, `status: str`, `acked_at: float|null`, `ack_source: str|null`.
- **Response** `200`: service-defined ack result dict (includes acked/not-found state per `backend/README.md`'s documented `acked=false, status=not_found` behavior for unknown `command_id`).

---

## Engine Telemetry (`/api/v1/engine-telemetry`) — `app/features/engine_telemetry/`

Plain `BaseModel`, `extra="forbid"`.

### `POST /engine-telemetry`
- **Auth**: Internal service.
- **Request body** (`EngineTelemetryIngestRequest`): `ts`, all packet/queue/ML counters (`packets_received_total, packets_received_per_30s, packets_processed_total, packets_dropped_total, packets_lost_total` — all `≥0` required; `packet_loss_detected: bool = false`; `packet_queue_size, packet_queue_maxsize: int ≥0` required; `packet_queue_usage_percent: float ≥0` required; `active_sessions: int ≥0` required; `ml_predictions_total, ml_predictions_per_30s: int ≥0` required; `ml_processing_rate_per_30s: float ≥0` required; `last_ml_prediction_latency_ms: float ≥0` default 0.0; `application_attribution_available: bool = false`; `application_attribution_note: str` (1–512) required; `active_network_exchanges: NetworkExchange[]` default `[]`, each `{source_ip, destination_ip, source_port?, destination_port?, protocol (0–255), packet_count?, byte_count?, duration?}`).
- **Response** `200`: `EngineTelemetryIngestResponse` — `{ accepted, packets_received_total, packet_loss_detected, active_sessions, packet_queue_size }`.
- **Internal flow**: persists an `engine_telemetry_snapshots` row; this is the write path that `GET /health/runtime*` reads from.

---

## Block Events (`/api/v1/block-events`) — `app/features/block_events/`

Plain `BaseModel`.

### `POST /block-events/upsert`
- **Auth**: Internal service.
- **Request body** (`BlockEventUpsertRequest`): `event_id, timestamp, source_ip, action_taken, reason, detection_method` required; `session_id, source_port, destination_ip, destination_port, protocol` optional.
- **Response**: `201` created / `200` updated (upsert on `event_id`) — `{ "created": bool, "event": BlockEventResponse }`.

---

## Blocked IPs (`/api/v1/blocked-ips`) — `app/features/blocked_ips/`

Plain `BaseModel`. All routes: Auth = Session. **None of these routes touch the firewall directly** — they queue commands for the IDS engine to pick up via `GET /engine-commands` (see Architecture: Response Engine).

### `GET /blocked-ips`
- **Parameters** (query): `status: str|null` (free-text description "blocked|watchlisted|unblocked" — not enum-constrained in the schema, just documented).
- **Response** `200`: `BlockedIPItem[]` — `ip_address, status, reason, first_detected, last_detected, total_attempts, attack_types (list[str]), last_action, source`.

### `POST /blocked-ips`
- **Request body** (`ManualBlockRequest`): `ip_address: IPvAnyAddress`, `reason: str` (default `"manual block request"`), `duration_seconds: int` (1–86400, default 300).
- **Response** `200`: service-defined command-queue confirmation data (message: "Manual block command queued").
- **Internal flow**: `BlockedIPService.manual_block()` enqueues an `engine_commands` row (`action="block"`) for the runtime's `BackendCommandPoller` to pick up and execute — the block doesn't happen synchronously in this request.

### `DELETE /blocked-ips/{ip_address}`
- **Parameters** (path): `ip_address: str`.
- **Response** `200`: queue confirmation (message: "Manual unblock command queued"); same async-via-`engine_commands` pattern (`action="unblock"`).

### `POST /blocked-ips/{ip_address}/watchlist`
- **Parameters** (path): `ip_address: str`. Router builds a `ManualWatchlistRequest(ip_address=ip_address)` internally — no request body accepted on the wire beyond the path param.
- **Response** `200`: queue confirmation (message: "Manual watchlist command queued").

### `GET /blocked-ips/{ip_address}/activity`
- **Parameters** (path): `ip_address: str`.
- **Response** `200`: `BlockedIPActivityItem[]` — `event_id, timestamp, action_taken, reason, detection_method, session_id, source_port, destination_ip, destination_port, protocol`.

---

## Notifications (`/api/v1/notifications`) — `app/features/notifications/`

No dedicated schema file (router builds/returns plain dicts from the service). Auth = Session on both routes.

### `POST /notifications/read-all`
- **Response** `200`: service-defined result dict (message: "Notifications marked as read").

### `POST /notifications/{notification_id}/read`
- **Parameters** (path): `notification_id: str`.
- **Response** `200`: service-defined result dict (message: "Notification marked as read").
- **Error responses**: none feature-specific defined (no `notifications` exceptions.py content) — a missing ID's behavior depends on the service implementation, not surfaced as a named exception here.

---

## Dashboard (`/api/v1/dashboard`) — `app/features/dashboard/`

All routes: Auth = Session. No feature-specific exceptions file — errors are either global 422/500 or a soft "not found" (see incident routes below).

### `GET /dashboard/summary`
- **Response** `200`: `DashboardSummaryResponse` — `total_threats, total_sessions, threats_today, active_sessions, blocked_ips, blocked_events_today, watchlisted_ips, high_severity_threats, packet_queue_usage_percent (default 0.0), packets_received_per_30s (default 0), ml_predictions_per_30s (default 0), packet_loss_detected (default false), last_ml_prediction_latency_ms (default 0.0)`.

### `GET /dashboard/attack-distribution`
- **Response** `200`: `DistributionItem[]` — `{ label, count }`.

### `GET /dashboard/threats-over-time`
- **Response** `200`: `TimeseriesItem[]` — `{ bucket, count }`.

### `GET /dashboard/block-actions-over-time`
- **Response** `200`: `TimeseriesItem[]`.
- **Internal flow**: grouped hourly from persisted `BlockEvent` rows (fallback source when durable `network_threat_rollups` aren't available — `backend/CHECKLIST.md`).

### `GET /dashboard/network-threat-rollups`
- **Parameters** (query): `limit` (1–720, default 48).
- **Response** `200`: `NetworkThreatRollupItem[]` — `bucket_start, bucket_size, network_activity_total, threat_event_total, blocked_event_total, threat_rate`.

### `GET /dashboard/top-source-ips`
- **Parameters** (query): `limit` (1–50, default 10).
- **Response** `200`: `TopSourceIPItem[]` — `{ source_ip, count }`.

### `GET /dashboard/top-destination-ports`
- **Parameters** (query): `limit` (1–50, default 10).
- **Response** `200`: `TopDestinationPortItem[]` — `{ destination_port, count }`.

### `GET /dashboard/model-metrics`
- **Response** `200`: `DashboardModelMetricsResponse` — `xgbooster_confidence, xgbooster_detection_rate, decision_tree_confidence, decision_tree_precision, sqli_confidence, sqli_precision` (field name `xgbooster` is spelled this way in the schema, not a typo introduced here).

### `GET /dashboard/incidents/{incident_id}`
- **Parameters** (path): `incident_id: str`.
- **Response**: **`200` with `data: null`** and message `"Incident not found"` if no match — **not a 404**, this is a deliberate soft-miss pattern specific to this route (differs from `/threats/{id}` and `/sessions/{id}`, which do raise 404). On match: `200` with `DashboardIncidentDetailResponse` — `{ incident: DashboardIncidentItem, related_sessions: dict[], related_audit: DashboardAuditItem[], telemetry_snapshot: dict|null }`.

### `GET /dashboard/incidents/{incident_id}/report`
- Same soft-miss `200`/`null`/"Incident not found" pattern as above. On match: `DashboardIncidentReportResponse` — `{ detail: DashboardIncidentDetailResponse, markdown: str, csv: str, generated_at: datetime }`.

### `GET /dashboard/history`
- **Parameters** (query): `limit` (1–240, default 30), `offset` (≥0).
- **Response** `200`: `PaginatedEngineTelemetryHistoryResponse` (same shape as `/health/runtime/history`).

### `GET /dashboard/incidents`
- **Parameters** (query): `limit` (1–240, default 30), `offset` (≥0).
- **Response** `200`: `{ items: DashboardIncidentItem[], total_count, limit, offset }` — sourced from `alerts` rows, field-mapped inline in the router (`incident_id = item.event_id`, plus `dedup_key, prediction, severity, confidence, action, source, status, first_seen_at, last_seen_at, occurrence_count, threat_id, detection_method, action_taken, session_id, source_ip, destination_ip, source_port, destination_port, protocol, risk_score, is_final`).

### `GET /dashboard/audit`
- **Parameters** (query): `limit` (1–240, default 30), `offset` (≥0).
- **Response** `200`: `{ items: DashboardAuditItem[], total_count, limit, offset }` — sourced from `block_events` rows.

---

## SQL Injection (`/api/v1/sql-injection`) — `app/features/sql_injection/`

Plain `BaseModel`.

### `POST /sql-injection/decide`
- **Auth**: **None** — no dependency of either kind on this route.
- **Request body** (`SQLDecisionRequest`): `request_id: str` (1–128), `ts: datetime`, `source: str` (1–64), `query: str` (min 1, unbounded max), `detected: bool`, `confidence: float` (0–1), `reason: str|null` (≤255).
- **Response** `200`: `SQLDecisionResponse` — `{ request_id, decision ("allow"|"block"), http_status (200|400, as a field in the 200-wrapped body — not the actual HTTP status of this call), detected, confidence, reason }`.
- **Error responses**: `422 SQL_INJECTION_PAYLOAD_INVALID` (`SQLInjectionPayloadValidationException`, exists but not raised in the current `service.decide()` path — reserved for stricter validation) beyond global 422.
- **Internal flow — important**: `SQLInjectionService.decide()` does **not run any detection logic**. It trusts the caller-supplied `detected`/`confidence`/`reason` verbatim, computes `decision = "block" if detected else "allow"` and `http_status = 400 if detected else 200`, truncates `query` to a 255-char `query_preview`, and persists a `sql_injection_events` row. Idempotent on `request_id`: a repeat call with the same `request_id` returns the stored decision without re-deriving it. See `docs/architecture.md` (SQL Injection Detection Architecture) for why — the actual detection model is external to this repository.

---

## Realtime (`/api/v1/realtime`) — `app/features/realtime/`

Plain `BaseModel`, `extra="forbid"` on the concrete message types. **None of these five routes have an auth dependency of either kind.**

### `WS /realtime/ws`
- **Auth**: None.
- **Protocol**: client connects, server registers it with `realtime_manager`; the handler then only calls `websocket.receive_text()` in a loop and discards the content — **it does not act on anything the client sends**, this channel is push-only from the server's side. Disconnects (`WebSocketDisconnect` or any other exception) deregister the client.
- **Server → client messages**: JSON payloads matching one of `RealtimeAlertMessage`, `RealtimeSessionMessage`, `RealtimeBlockedIPMessage`, `RealtimeDashboardMetricsMessage` (see field lists below), pushed via the `/broadcast*` routes.

### `POST /realtime/broadcast`
- **Request body** (`RealtimeAlertMessage`): `event_id, ts, prediction, severity, confidence, action, source` required; `source_ip, destination_ip, source_port, destination_port, protocol, attack_type, confidence_score, action_taken, status, detection_method, session_id, packet_count, byte_count, flow_duration, ml_prediction` optional; `response_history: str[]` default `[]`.
- **Response** `200`: `{ "broadcast": true }`.
- **Internal flow**: `RealtimeService.broadcast_alert()` fans the payload out to every connected WebSocket client via `realtime_manager`.

### `POST /realtime/broadcast/sessions`
- **Request body** (`RealtimeSessionMessage`): `session_id, ts, source_ip, destination_ip, protocol, packet_count, byte_count, risk_score, state` required; `start_time, end_time, source_port, destination_port, duration, ml_prediction, heuristic_result, action_taken` optional.
- **Response** `200`: `{ "broadcast": true }`.

### `POST /realtime/broadcast/blocked-ips`
- **Request body** (`RealtimeBlockedIPMessage`): `ip_address, status, source` required; `first_detected, last_detected, total_attempts, attack_types (default []), last_action, reason, command_status` optional.
- **Response** `200`: `{ "broadcast": true }`.

### `POST /realtime/broadcast/dashboard`
- **Request body** (`RealtimeDashboardMetricsMessage`, `extra="allow"` — the only realtime message that accepts arbitrary extra fields): `ts: datetime`, `metrics: dict[str, Any]`.
- **Response** `200`: `{ "broadcast": true }`.
- **Error responses**: `422 REALTIME_PAYLOAD_VALIDATION_FAILED` (`RealtimePayloadValidationException`) exists in `exceptions.py` but its trigger condition isn't visible in the router — presumably raised inside `RealtimeService` for a payload judged unsafe to broadcast.

Note: `RealtimeHealthMessage` and `RealtimeEnvelope` are defined in `schemas.py` but have **no corresponding router endpoint** — they appear to be for a planned `health_updates`/generic-channel broadcast path (`RealtimeEnvelope.channel` lists `logs_updates`, `traffic_updates`, `health_updates` as literal options) not yet wired up. See `docs/roadmap.md` (dashboard live-data items).

---

## Frontend Consumption

The Next.js frontend calls this API via `NEXT_PUBLIC_IDS_REST_BASE_URL`/`IDS_REST_BASE_URL` (REST) and `NEXT_PUBLIC_IDS_WS_URL` (`/realtime/ws`). Client wrappers: `frontend/src/lib/backend/*.ts`, one per resource.
