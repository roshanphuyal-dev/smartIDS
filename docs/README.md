# smartIDS or (Heimdall IDS)

smartIDS is a smart intrusion detection system built with Python and modern web technologies. It captures realtime threats, analyzes traffic with machine learning, raises alerts, and blocks malicious activity automatically.

## Key Features

- Realtime threat detection using Python and ML models
- Alerting for suspicious activity
- Automated threat blocking
- FastAPI backend for API and management
- PostgreSQL database for logging and persistence
- Next.js frontend to visualize system status for regular users

## Architecture

1. **Data capture and analysis**
   - Python components collect network or event data in realtime
   - Machine learning models analyze behavior and detect anomalies
   - Threats are classified and prioritized

2. **Backend**
   - FastAPI provides REST endpoints for alerts, threat status, and control operations
   - PostgreSQL stores event logs, alert history, and system state
   - The backend coordinates detection, alerting, and blocking actions

3. **Frontend**
   - Next.js shows a clean dashboard for non-technical users
   - Displays realtime alerts, threat summaries, and system health
   - Makes it easy to understand what is happening without technical jargon

## Components

- `python/` - Core detection engine and ML pipeline
- `backend/` - FastAPI service and PostgreSQL integration
- `frontend/` - Next.js dashboard for monitoring

## Getting Started

1. Install dependencies for the backend and frontend.
2. Configure PostgreSQL connection settings.
3. Start the FastAPI server.
4. Run the Python detection service.
5. Launch the Next.js frontend.

## What It Provides

- Continuous monitoring of incoming events
- Machine learning driven threat detection
- Alerts for suspicious activity
- Blocking of confirmed threats
- User-friendly visualization of system events

## Goals

- Make intrusion detection accessible to regular users
- Provide realtime visibility into security events
- Help teams react quickly to threats
- Combine ML intelligence with practical alerting and blocking

## Future Development

SmartIDS now has a strong core. The next stage is to evolve it into an enterprise-ready platform in layers, while keeping runtime correctness first.

### Dual-Mode Architecture (Web + Desktop)

Build one shared FastAPI backend codebase that runs in two modes:

- **Server mode (`APP_MODE=server`)**: web backend for browser dashboard, multi-client management, SOC workflows.
- **Agent mode (`APP_MODE=agent`)**: local backend service for desktop distribution (`.exe` / `.deb`), running on endpoint hosts.

Both modes should share the same core services (alerts, policies, ML event handling), and use mode-specific adapters for auth, storage, and transport.

### Most Valuable Next Features (Enterprise Priority)

- **Model/runtime governance**: model versioning, schema hash checks, drift monitoring, and rollback when live confidence or false-positive rate degrades.
- **Production alert pipeline**: severity scoring, dedup/correlation, suppression windows, escalation policies.
- **Case management hooks**: MITRE ATT&CK tagging, evidence snapshots, SIEM/SOAR export (Splunk, Sentinel, Elastic, QRadar).
- **Operational reliability**: persistent alert spool/queue, retry with backoff, delivery status tracking.
- **Security hardening**: API key/mutual auth for forwarding, signed payloads, strict validation, tamper-evident audit logs.
- **Performance/SLOs**: metrics for packets/sec, queue depth, drop rate, inference latency, alert latency; health endpoints; Prometheus/Grafana.

### Detection and ML Upgrades

- **Multi-stage detection**: fast heuristic + early model first, completed-flow classifier as confirmation.
- **Threshold calibration**: per-class confidence thresholds (not one global threshold), tuned by risk and SOC capacity.
- **Continuous validation**: nightly replay tests + shadow inference on pcap samples before rollout.
- **Data quality guardrails**: runtime checks for null spikes, protocol drift, and class imbalance alarms.

### Platform and Architecture Upgrades

- **Response abstraction**: cross-platform firewall adapters with policy engine and cooldown timers.
- **RBAC + multitenancy**: role-based access, tenant-scoped alerts/models, tenant-specific thresholds/policies.
- **Compliance-ready logging**: immutable audit trail for detections and response actions (who/what/when/why).
- **Deployment maturity**: containerization, config profiles, blue/green model deploys, secrets management.

### Best Immediate Sequence

1. Add runtime metrics and health endpoints.
2. Add alert dedup/correlation and severity policy engine.
3. Add secure alert transport (auth, retries, dead-letter queue).
4. Add model governance (versioning, schema pinning, rollback).
5. Add SIEM export connectors.

### Optional Next Artifact

Create an `enterprise_roadmap.md` with 2-week milestones mapped to exact files/modules in this repository.

## License

Distributed under the MIT License.  