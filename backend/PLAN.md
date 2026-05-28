# Backend Dual-Mode Plan (Web + Desktop Agent)

## Goal

Build one FastAPI backend codebase that runs in two modes:

- `server` mode: web backend for browser dashboard and multi-client management.
- `agent` mode: local desktop service (for `.exe` / `.deb`) running on endpoint hosts.

Both modes share core IDS business logic and API contracts.

## Mode Strategy

Use an environment variable:

- `APP_MODE=server`
- `APP_MODE=agent`

At startup, load mode-specific adapters for auth, storage, and transport.

## Proposed Backend Structure

```text
backend/
  app/
    main.py
    config.py
    api/
      routes_health.py
      routes_alerts.py
      routes_events.py
      routes_admin.py
    core/
      models.py
      schemas.py
      services/
        alert_service.py
        policy_service.py
    adapters/
      auth/
        server_auth.py
        agent_auth.py
      storage/
        server_db.py
        agent_local_db.py
      transport/
        server_push.py
        agent_local_push.py
```

## Phase Plan

### Phase 1: Foundation (Now)

1. Create `backend/app/main.py` with app factory pattern.
2. Add `backend/app/config.py` for env-driven mode config.
3. Add health + alerts endpoints.
4. Move current stub logic from `backend/main.py` into structured modules.

Deliverable: FastAPI app runs in `server` and `agent` mode with same routes.

### Phase 2: Shared Domain Layer

1. Define Pydantic schemas for alerts/events.
2. Add `alert_service.py` for dedup, severity, normalization.
3. Keep IDS-to-backend contracts stable (`attack_type`, `confidence`, `blocked`, `block_status`).

Deliverable: shared service layer independent of deployment mode.

### Phase 3: Adapter Split

1. Auth adapters:
   - `server_auth.py` (JWT/API-key + RBAC)
   - `agent_auth.py` (local token/minimal auth)
2. Storage adapters:
   - `server_db.py` (PostgreSQL)
   - `agent_local_db.py` (SQLite)
3. Transport adapters:
   - `server_push.py` (websocket/SSE for browser)
   - `agent_local_push.py` (localhost UI bridge)

Deliverable: mode-specific behavior without forking APIs.

### Phase 4: Browser Dashboard Readiness

1. Add paginated query endpoints for alerts/events.
2. Add filtering (time range, attack type, severity, source IP).
3. Add websocket/SSE stream endpoint for live alerts.

Deliverable: browser dashboard can consume historical + live data.

### Phase 5: Desktop Packaging Readiness

1. Add `agent` startup profile (localhost bind only).
2. Add local persistence + retention policy.
3. Add stable local API contract for desktop shell.

Deliverable: backend reusable for `.exe`/`.deb` packaging.

## Non-Functional Requirements

- Keep API contracts identical across modes.
- Enforce strict input validation.
- Add structured logging with request IDs.
- Add metrics endpoints for health and throughput.
- Keep secrets in environment variables, never hardcoded.

## Immediate Next Tasks

1. Create `backend/app/` structure and app factory.
2. Move current `/alerts` and `/` dashboard endpoints into modular routes.
3. Add `APP_MODE` config and mode switch hooks (stub adapters first).
