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

- `packet_capture/` - Scapy capture, parsing, runtime processor, and backend forwarding
- `traffic_engine/` - Session and flow tracking
- `feature_engine/` - Runtime feature extraction and safe statistics
- `ml/` - Feature schema, CICIDS2017 preparation, training, evaluation, and model artifacts
- `response_engine/` - Reactive mitigation and firewall abstraction
- `backend/` - FastAPI service, PostgreSQL integration, auth, realtime, and control APIs
- `frontend/` - Next.js dashboard for monitoring

## Getting Started

1. Install dependencies for the backend and frontend.
2. Configure PostgreSQL connection settings.
3. Start the FastAPI server.
4. Run the Python detection service.
5. Launch the Next.js frontend.

## CICIDS2017 Dataset Preparation

Prepare canonical train/test files only from a verified raw CICIDS2017 CSV export that contains every field in `ml/features/schema.py`:

```powershell
.\.venv_windows\Scripts\python.exe -m ml.datasets.prepare_cicids2017 `
  --source C:\path\to\raw-cicids2017 `
  --output-dir ml\data
```

The source may be one CSV or a directory of CSV files. The command validates all canonical fields before writing, creates a seeded stratified split, and records hashes, row counts, feature order, and label distributions in `ml/data/cicids2017_dataset_metadata.json`.

Existing outputs require `--force`. The current bundled CSVs are not valid preparation sources because they lack `protocol`, `syn_flag_count`, `rst_flag_count`, and `urg_flag_count`.

### Train, Verify, And Activate The Model

After dataset preparation succeeds, run the complete model build:

```powershell
.\.venv_windows\Scripts\python.exe -m ml.training.build_cicids2017_model
```

This command validates dataset hashes and schema, trains in a temporary staging directory, evaluates the model, verifies the staged files through the runtime artifact loader, runs a sample prediction, writes a model manifest and sample input/output, and only then replaces `ml/saved_models`.

If any step fails, the existing active model directory remains unchanged. Stop the IDS runtime before activation on Windows so open model files do not block the directory swap.

Checked-in contract examples:

- `ml/contracts/cicids2017_training_row.example.json`
- `ml/contracts/live_prediction_input.example.json`
- `ml/contracts/live_prediction_output.example.json`

Each successful build also writes artifact-specific examples:

- `ml/saved_models/live_compatible_sample_input.json`
- `ml/saved_models/live_compatible_sample_output.json`
- `ml/saved_models/live_compatible_model_manifest.json`

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

### Linux Lab Plan

Use `docs/LINUX_TEST_LAB.md` for the isolated disposable-VM validation workflow.

## License

Distributed under the MIT License.
