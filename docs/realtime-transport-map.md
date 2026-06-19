# SmartIDS Realtime Transport Map

This document records which SmartIDS frontend and engine features use WebSockets, polling, one-time fetches, or server-rendered data snapshots.

It is based on the current code in the repository as of 2026-06-17.

## Summary

SmartIDS currently uses a hybrid transport model:

- WebSockets for live event streams such as threats, sessions, blocked IP updates, and connection status.
- WebSocket plus polling for dashboard summary metrics and charts.
- On-demand fetches for detail drawers and activity panels.
- Server-rendered fetches for initial page data.
- Polling for IDS engine command delivery to the background runtime.

This is not a polling-only app and not a WebSocket-only app.

## Transport Table

| Area | Page or feature | Current transport | Code reference | Notes |
|---|---|---|---|---|
| Frontend | Dashboard header realtime badge | WebSocket | [`frontend/src/components/dashboard/realtime-status-badge.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/realtime-status-badge.tsx:24) | Opens its own socket just to monitor connection state. |
| Frontend | Global threat toast | WebSocket | [`frontend/src/components/dashboard/global-threat-toast.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/global-threat-toast.tsx:8) | Uses `threat_notifications`. |
| Frontend | Overview status strip | WebSocket + polling | [`frontend/src/components/dashboard/service-status-strip.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/service-status-strip.tsx:7) | Uses `useDashboardRealtime()`. |
| Frontend | Overview metrics cards and mini charts | WebSocket + polling | [`frontend/src/components/dashboard/overview-metrics.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/overview-metrics.tsx:26) | Uses `useDashboardRealtime()`. |
| Frontend | Overview charts | WebSocket + polling | [`frontend/src/components/dashboard/overview-charts.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/overview-charts.tsx:17) | Uses `useDashboardRealtime()`. |
| Frontend | Overview top lists | Server-rendered fetch | [`frontend/src/app/(dashboard)/overview/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/overview/page.tsx:15) | Initial page snapshot only. |
| Frontend | Overview recent activity feed | Server-rendered fetch | [`frontend/src/app/(dashboard)/overview/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/overview/page.tsx:114) | Not subscribed to live updates. |
| Frontend | Overview control-center blocked IP cards | Server-rendered fetch | [`frontend/src/app/(dashboard)/overview/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/overview/page.tsx:89) | Not subscribed to live updates. |
| Frontend | Analytics charts | WebSocket + polling | [`frontend/src/app/(dashboard)/analytics/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/analytics/page.tsx:10) | Uses `useDashboardRealtime()`. |
| Frontend | Threat table live updates | WebSocket | [`frontend/src/components/dashboard/threat-reports-table.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/threat-reports-table.tsx:80) | Uses `threat_notifications`. |
| Frontend | Threat page initial list/filter state | Server-rendered fetch | [`frontend/src/app/(dashboard)/threats/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/threats/page.tsx:62) | Backend fetch first, DB fallback second. |
| Frontend | Threat detail dialog | On-demand fetch | [`frontend/src/components/dashboard/threat-reports-table.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/threat-reports-table.tsx:176) | Fetched only when a row is opened. |
| Frontend | Threat live notifications panel | WebSocket | [`frontend/src/components/dashboard/threat-live-notifications.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/threat-live-notifications.tsx:28) | Uses `threat_notifications`. |
| Frontend | Sessions table live updates | WebSocket | [`frontend/src/components/dashboard/sessions-live-table.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/sessions-live-table.tsx:33) | Uses `session_logs`. |
| Frontend | Sessions page initial list/filter state | Server-rendered fetch | [`frontend/src/app/(dashboard)/sessions/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/sessions/page.tsx:44) | Backend fetch first, DB fallback second. |
| Frontend | Session detail dialog | On-demand fetch | [`frontend/src/components/dashboard/sessions-live-table.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/sessions-live-table.tsx:98) | Fetched only when a row is opened. |
| Frontend | Blocked IP table live updates | WebSocket | [`frontend/src/components/dashboard/blocked-ips-live-table.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/blocked-ips-live-table.tsx:43) | Uses `blocked_ip_updates`. |
| Frontend | Blocked IP page initial list/filter state | Server-rendered fetch | [`frontend/src/app/(dashboard)/blocked-ips/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/blocked-ips/page.tsx:31) | Backend fetch first, DB fallback second. |
| Frontend | Blocked IP activity dialog | On-demand fetch | [`frontend/src/components/dashboard/blocked-ips-live-table.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/blocked-ips-live-table.tsx:85) | Fetched only when a row is opened. |
| Frontend | Dashboard metrics live indicator | WebSocket | [`frontend/src/components/dashboard/dashboard-metrics-live-indicator.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/dashboard-metrics-live-indicator.tsx:7) | Uses `dashboard_metrics` only to show last live push. |
| Frontend | Traffic page | Server-rendered fetch | [`frontend/src/app/(dashboard)/traffic/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/traffic/page.tsx:14) | Not live after render. |
| Frontend | Logs page | One-time client fetch | [`frontend/src/app/(dashboard)/logs/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/logs/page.tsx:20) | Fetches once in `useEffect`, no polling or socket. |
| Frontend | Health page | Server-rendered fetch | [`frontend/src/app/(dashboard)/health/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/health/page.tsx:9) | Not live after render. |
| Frontend core | Generic channel hook | WebSocket | [`frontend/src/lib/realtime/use-realtime-channel.ts`](D:/Roshan/Projects/smartIDS/frontend/src/lib/realtime/use-realtime-channel.ts:24) | Core hook for channelized live updates. |
| Frontend core | Dashboard aggregate realtime hook | WebSocket + polling | [`frontend/src/lib/realtime/use-dashboard-realtime.ts`](D:/Roshan/Projects/smartIDS/frontend/src/lib/realtime/use-dashboard-realtime.ts:105) | Subscribes to `dashboard_metrics`, polls REST every 30s. |
| Backend | Realtime socket endpoint | WebSocket | [`backend/app/features/realtime/router.py`](D:/Roshan/Projects/smartIDS/backend/app/features/realtime/router.py:19) | FastAPI websocket route at `/api/v1/realtime/ws`. |
| Backend | Realtime connection manager | WebSocket | [`backend/app/features/realtime/manager.py`](D:/Roshan/Projects/smartIDS/backend/app/features/realtime/manager.py:6) | Broadcasts JSON to connected clients. |
| Engine | Backend command intake for IDS runtime | Polling | [`packet_capture/sniffer_service.py`](D:/Roshan/Projects/smartIDS/packet_capture/sniffer_service.py:219) | Poll loop fetches commands on an interval. |
| Engine | Command poller implementation | Polling | [`response_engine/backend_command_poller.py`](D:/Roshan/Projects/smartIDS/response_engine/backend_command_poller.py:17) | Uses HTTP GET and POST ack. |

## What Should Stay WebSocket

These are good WebSocket candidates and should remain WebSocket-driven:

- Threat notifications
- Session log updates
- Blocked IP updates
- Global threat toasts
- Realtime connection status indicators

Why:

- They are event streams.
- Operators benefit from immediate push delivery.
- The payloads are incremental and naturally map to append/update UI behavior.

## What Should Stay Hybrid

These are better as WebSocket plus polling rather than WebSocket-only:

- Dashboard summary metrics
- Dashboard charts
- Attack distribution
- Model metrics trend data

Why:

- Aggregates can drift if a client misses events during reconnects.
- Polling gives periodic state reconciliation.
- The current polling cadence is modest and operationally reasonable.
- A push-only design would need stronger snapshot semantics and replay/recovery logic.

## What Should Stay On-Demand Fetch

These are better as fetch-on-open rather than socket channels:

- Threat detail dialog
- Session detail dialog
- Blocked IP activity dialog

Why:

- The user explicitly requests the data.
- It avoids maintaining unnecessary per-row subscriptions.
- The data is detail-oriented rather than stream-oriented.

## What Should Stay Polling

The IDS runtime command path is a good polling candidate:

- Engine command queue -> poll -> ack

Why:

- The runtime is a background Python service rather than a browser tab.
- Polling keeps the control plane simple and resilient.
- Command latency requirements here are modest compared with alert visualization.
- It avoids adding a long-lived socket dependency to the IDS runtime control loop.

## Current Issues Worth Fixing

### 1. `useDashboardRealtime()` is likely duplicated on the same page

This is the biggest transport issue in the current frontend.

On `/overview`, these components each call `useDashboardRealtime()` independently:

- [`ServiceStatusStrip`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/service-status-strip.tsx:7)
- [`OverviewMetricsGrid`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/overview-metrics.tsx:26)
- [`OverviewCharts`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/overview-charts.tsx:17)

Each hook instance creates:

- its own WebSocket subscription to `dashboard_metrics`
- its own 30-second polling loop

That means one page can open multiple sockets and perform duplicate polling for the same dashboard aggregate state.

Recommended change:

- Lift `useDashboardRealtime()` to a shared provider or page-level parent.
- Pass the resulting state down via props or context.
- Keep one dashboard aggregate socket and one polling loop per page, not one per component.

### 2. `RealtimeStatusBadge` opens a separate socket just for connection status

[`RealtimeStatusBadge`](D:/Roshan/Projects/smartIDS/frontend/src/components/dashboard/realtime-status-badge.tsx:24) creates its own socket connection instead of reusing an existing shared realtime connection state.

This is not broken, but it is wasteful.

Recommended change:

- Reuse shared socket connection state from a provider or shared hook.
- Avoid opening a dedicated socket only to color a badge.

### 3. Some pages are labeled "live" but are not truly live after render

Examples:

- [`traffic/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/traffic/page.tsx:14)
- [`health/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/health/page.tsx:9)
- [`logs/page.tsx`](D:/Roshan/Projects/smartIDS/frontend/src/app/(dashboard)/logs/page.tsx:20)

Current behavior:

- `traffic` and `health` are server-rendered snapshots only.
- `logs` fetches once on mount, then stops.

If the product expectation is "realtime" for these pages, they are not fully meeting that expectation.

Recommended change:

- If true live behavior is required, connect them to existing socket channels or add periodic polling where appropriate.
- If not required, rename or describe them as snapshots to avoid misleading operators.

### 4. Dashboard WebSocket pushes currently update only part of dashboard state

[`useDashboardRealtime()`](D:/Roshan/Projects/smartIDS/frontend/src/lib/realtime/use-dashboard-realtime.ts:121) accepts `dashboard_metrics` pushes, but the pushed payload handling only updates summary-style fields and derived series.

Timeline, distribution, and model metrics still depend on the polling path for full refresh.

This is acceptable for a hybrid design, but it means the dashboard is not truly push-complete.

Recommended change:

- Keep hybrid behavior unless you intentionally redesign backend push payloads.
- If you want richer push behavior, extend the `dashboard_metrics` payload contract to include snapshot-ready aggregates.

## Recommended Transport Direction

### Keep as-is conceptually

The current transport choices are broadly correct:

- WebSocket for event streams
- Hybrid for dashboard aggregates
- On-demand fetch for row details
- Polling for runtime command intake

### Change implementation details

The main change needed is not "replace polling with WebSockets everywhere."

The main change needed is:

- consolidate duplicated dashboard realtime subscriptions and polling into a shared state source
- reuse socket connection state instead of opening extra sockets for status-only UI

Those changes improve correctness, reduce redundant network activity, and fit the current architecture better than a WebSocket-only rewrite.
