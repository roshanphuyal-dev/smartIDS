# Dashboard Analytics Persistence Design

## Goal
Persist the dashboard analytics data that is currently assembled in-memory or from transient realtime state, then serve the dashboard from backend-owned database records instead of temporary client-side snapshots.

## Current State
- Overview cards still mix persisted backend counts with realtime telemetry values for queue usage, packets per 30s, ML predictions per 30s, and packet-loss state.
- The Analytics page builds its throughput chart from the frontend realtime history buffer instead of a durable history source.
- Dashboard charts already read from backend aggregate endpoints, but the browser still keeps its own short-lived telemetry history for display repair and freshness.

## Proposed Approach
Use a dedicated backend persistence table for dashboard analytics snapshots.

Each persisted snapshot should capture:
- timestamp
- dashboard summary metrics
- attack distribution
- threat timeline
- top source IPs
- top destination ports
- optional runtime health summary fields needed for the current UI

The backend continues to compute the aggregates from canonical source tables (`alerts`, `network_sessions`, `block_events`, and `engine_telemetry_snapshots`), but it also writes a durable snapshot row whenever dashboard metrics are refreshed.

## Backend Changes
1. Add a new `dashboard_analytics_snapshots` table and SQLAlchemy model.
2. Add a repository/service pair to create and list snapshots.
3. Extend the dashboard service so each summary refresh can also persist one analytics snapshot.
4. Add backend query endpoints for:
   - latest analytics snapshot
   - paginated analytics history
5. Keep the existing aggregate queries as the source of truth for calculation, but stop relying on ephemeral frontend-only chart history.

## Frontend Changes
1. Remove the temporary packet counter and ML prediction rate cards from the dashboard overview.
2. Update the Analytics page to load persisted analytics snapshots from backend endpoints.
3. Keep realtime websocket updates for freshness, but make them a repair/overlay layer instead of the only source of chart history.
4. Preserve the rest of the dashboard layout and summary cards.

## Data Rules
- No browser-facing page should write directly to Postgres.
- Dashboard analytics persistence must remain backend-owned.
- The persisted snapshot should be additive and non-destructive; no existing alert/session/telemetry tables should be rewritten.
- Empty or missing analytics data should render as empty states rather than errors.

## Success Criteria
- Dashboard analytics charts still render when websocket history is absent.
- Analytics history survives a page reload because the source comes from the database.
- Overview no longer shows the packet counter card or ML parsing-rate card.
- Existing summary cards for sessions, threats, blocked IPs, queue usage, and packet loss still work.

## Verification
- Run backend syntax checks and targeted tests for the new dashboard analytics repository/service/routes.
- Run frontend typecheck and build after removing the temporary cards and switching chart data loading.
- Smoke-test the dashboard after persisting a few analytics snapshots to confirm reload-safe history.
