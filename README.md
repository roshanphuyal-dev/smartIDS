# smartIDS #Heimdall IDS

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

## License

Distributed under the MIT License.  