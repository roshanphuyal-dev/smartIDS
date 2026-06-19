# Full Dashboard Live-Data Architecture for SmartIDS

## Summary

Rework the SmartIDS dashboard into a database-first, backend-mediated, live-update system across:

- `/overview`
- `/analytics`
- `/traffic`
- `/logs`
- `/health`
- `/threats`
- `/sessions`
- `/blocked-ips`
- shared status badges, toasts, and notification surfaces

Core design:

1. IDS engine and backend services persist first.
2. Backend exposes query-oriented REST endpoints.
3. Backend emits small WebSocket update envelopes.
4. Frontend uses WebSocket plus polling for freshness and correctness.
5. Durable history is kept for events, sessions, block events, telemetry, and alert summaries.

## Source Of Truth By Page

| Page | Primary source of truth | Secondary live mechanism |
| --- | --- | --- |
| `/overview` | dashboard aggregate queries over alerts, sessions, block events, telemetry | `dashboard_metrics` WebSocket + polling |
| `/analytics` | dashboard aggregate and historical rollup queries | `dashboard_metrics` WebSocket + polling |
| `/traffic` | `network_sessions` | `traffic_updates` WebSocket + polling |
| `/logs` | `ids_events` | `logs_updates` WebSocket + polling |
| `/health` | `engine_telemetry_snapshots` plus rollups | `health_updates` WebSocket + polling |
| `/threats` | `alerts` or threat query model | `threat_notifications` WebSocket + polling |
| `/sessions` | `network_sessions` | `session_logs` WebSocket + polling |
| `/blocked-ips` | `block_events` aggregate read model | `blocked_ip_updates` WebSocket + polling |

## Durable Storage Strategy

- `ids_events` remains append-only durable IDS event storage and becomes the canonical source for `/logs`.
- `network_sessions` remains the canonical source for `/traffic` and `/sessions`.
- `alerts` remains the deduplicated alert and incident layer for `/threats`, `/overview`, and `/analytics`.
- `block_events` remains the canonical source for `/blocked-ips`.
- `engine_telemetry_snapshots` is added as the persisted runtime telemetry source for `/health` and telemetry-backed dashboard health indicators.

## Required Backend Changes

- Persist telemetry snapshots before any realtime broadcast.
- Add or standardize REST endpoints:
  - `GET /api/v1/logs`
  - `GET /api/v1/traffic`
  - `GET /api/v1/health/runtime`
  - `GET /api/v1/health/runtime/history`
- Extend queryable persisted models where needed so filters are durable, indexed, and not derived only from JSON payloads.
- Add websocket channels:
  - `logs_updates`
  - `traffic_updates`
  - `health_updates`
- Keep websocket messages small and freshness-oriented.

## Required Frontend Changes

- Use backend-first adapters instead of legacy mock DB helpers for active routes.
- Apply the same pattern to each live page:
  - initial fetch
  - websocket freshness updates
  - periodic polling re-sync
  - reconnect/error/loading states
- Migrate `/traffic`, `/logs`, and `/health` first, then keep `/overview`, `/analytics`, `/threats`, `/sessions`, and `/blocked-ips` aligned to the same architecture.

## Rollout Sequence

1. Core backend foundation.
2. Shared frontend adapters and live hooks.
3. Migrate `/health`, `/logs`, `/traffic`, `/overview`, and `/analytics`.
4. Align the rest of the dashboard and remove remaining mock/derived legacy paths.

## Acceptance Goals

- New IDS events appear in `/logs`, update summary surfaces, and remain queryable from durable storage.
- Session updates appear in `/traffic` and `/sessions` from the same canonical session store.
- Telemetry spikes appear in `/health` live and remain available in historical queries.
- Realtime websocket misses are repaired by the next poll cycle.
- The frontend never receives raw logs directly from the IDS engine; the engine writes to the backend, the backend persists, and the frontend reads persisted data.
