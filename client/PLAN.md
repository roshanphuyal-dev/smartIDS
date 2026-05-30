# SmartIDS Frontend Plan

## Goal

Build a frontend UI for SmartIDS that presents live intrusion detection analytics, threat investigation workflows, session-level monitoring, and IP response management.

The frontend must consume live backend WebSocket events for real-time updates and use REST API calls for manual response actions such as block, unblock, watchlist, and IP activity lookup.

## Product Scope

Create four primary pages:

1. Main Dashboard
2. Threat Reports
3. Session Logs
4. Blocked IPs

The UI should focus on session-based IDS monitoring, not single-packet inspection. SmartIDS is a passive userland IDS, so wording must describe mitigation as blocking or responding to future traffic, not perfect inline prevention.

## Data Integration

### Live WebSocket Updates

Use backend WebSocket streams for real-time data such as:

- Dashboard metrics
- New threat notifications
- Updated session activity
- Threat timeline changes
- Blocked or watchlisted IP updates
- Traffic/session volume changes

### REST API Calls

Use backend API endpoints for user-triggered actions:

- Manually block an IP
- Remove an IP from the blocked list
- Move an IP to the watchlist
- Keep or confirm an IP as blocked
- Fetch IP activity history
- Fetch threat detail records
- Fetch paginated and filtered threat/session tables

## Page 1: Main Dashboard

The Main Dashboard is the landing page for live IDS visibility.

### Required Metrics

Display summary cards for:

- Total sessions
- Active sessions
- Threats detected today
- Threats blocked today
- Detection rate
- Model precision
- Model confidence
- False positive rate, when available

### Required Live Panels

Include real-time sections for:

- Live threat notifications
- Attack type distribution chart
- Threats over time chart
- Top source IPs
- Top attacked destination ports
- Traffic or session volume timeline

### Dashboard Behavior

- Update metrics from WebSocket events without requiring a full page refresh.
- Show loading, empty, and error states for all chart and metric data.
- Clearly distinguish detected threats from blocked threats.
- Avoid implying that all detected traffic was prevented; use language such as `blocked for future traffic`, `allowed`, or `watchlisted`.

## Page 2: Threat Reports

The Threat Reports page provides a searchable and inspectable list of detected threats.

### Threat Table Fields

Each threat row must show:

- Timestamp
- Threat ID
- Source IP
- Source port
- Destination IP
- Destination port
- Protocol
- Attack type
- Severity
- Confidence score
- Detection method: ML or heuristic
- Action taken: blocked, allowed, or watchlisted
- Status

### Threat Detail View

Selecting a threat row must open a detail view containing:

- Full session information
- Attack timeline
- Packet count
- Bytes transferred
- Flow duration
- Triggered rules
- ML prediction result
- Confidence score
- Response action history

### Threat Reports Behavior

- Support pagination for large threat lists.
- Support stable sorting by timestamp, severity, confidence, and status.
- Keep table rows compact, with detailed investigation data in the detail view.
- Refresh or append new threats from WebSocket events while preserving the user’s current filters where possible.

## Page 3: Session Logs

The Session Logs page shows live session-based logs rather than packet-level logs.

### Session Table Fields

Each session row must show:

- Timestamp
- Session ID
- Source IP
- Destination IP
- Source port
- Destination port
- Protocol
- Duration
- Packet count
- Byte count
- Session state
- Risk score
- ML prediction
- Heuristic result

### Required Filters

Provide filters for:

- Time range
- IP address
- Attack type
- Protocol
- Risk score
- Blocked, allowed, or watchlisted action state

### Session Logs Behavior

- Treat sessions as the main monitoring unit.
- Update active sessions from WebSocket events.
- Allow completed or expired sessions to remain available through API-backed history.
- Avoid rendering every packet as a separate log row.

## Page 4: Blocked IPs

The Blocked IPs page manages blocked and watchlisted IP addresses.

### IP Table Fields

Each IP row must show:

- IP address
- Status: blocked or watchlisted
- First detected time
- Last detected time
- Total attack attempts
- Attack types used
- Last action taken
- Block reason
- Source: automatic or manual

### Required Actions

Provide controls to:

- Manually block an IP using an input field
- Remove an IP from the blocked list
- Move an IP to the watchlist
- Keep an IP blocked
- View IP activity history
- Identify whether the activity was a single attempt or repeated attempts

### Blocked IPs Behavior

- Confirm destructive or security-sensitive actions before applying them.
- Show optimistic UI updates only if rollback behavior is implemented.
- Display action success and failure states clearly.
- Record whether a block came from automatic detection or a manual user action.

## Shared UI Requirements

- Use a consistent application shell with navigation for Dashboard, Threat Reports, Session Logs, and Blocked IPs.
- Provide responsive layouts for desktop and mobile.
- Use clear severity styling for normal, low, medium, high, and critical states.
- Include reusable table, filter, chart, status badge, metric card, and detail drawer/modal components.
- Include loading, empty, error, and reconnecting states for live data.
- Show WebSocket connection status in the UI.
- Ensure time values are consistently formatted and timezone-aware.

## Suggested Implementation Order

1. Initialize the frontend project structure inside `client`.
2. Add routing and the shared application shell.
3. Build API and WebSocket client modules.
4. Create reusable UI primitives: metric cards, tables, badges, filters, charts, and detail views.
5. Implement the Main Dashboard with mock or contract-based data first.
6. Implement Threat Reports and threat detail view.
7. Implement Session Logs with filtering.
8. Implement Blocked IPs with manual response actions.
9. Connect all pages to live WebSocket and REST API data.
10. Add validation, loading states, error states, and responsive polish.

## Acceptance Criteria

- All four required pages exist and are reachable from navigation.
- Dashboard metrics and live panels update from WebSocket data.
- Threat Reports shows the required table fields and opens a complete detail view.
- Session Logs shows session-level records, not individual packets.
- Blocked IPs supports manual block, unblock, watchlist, keep blocked, and activity history workflows.
- API and WebSocket failures are visible to the user.
- The UI avoids language that claims inline or perfect packet prevention.
