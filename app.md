# SmartIDS Agent Instructions

## Project Type

Realtime AI-assisted IDS with reactive mitigation (NOT inline IPS). Uses Scapy for passive sniffing - packets may reach applications before detection. Response engine blocks future traffic only.

## Architecture

```
Packet Capture → Packet Parsing → Session Building → Feature Extraction → ML Detection → Threat Decision → Response Engine → FastAPI/WebSocket → Dashboard
```

## Hybrid Packet Capture Architecture

- **Capture**: Dedicated thread for Scapy (blocking internally, not async-native)
- **Buffering**: Queue-based packet buffering
- **Processing**: AsyncIO consumers for parsing, session aggregation, feature extraction, ML inference

This separation prevents packet loss and realtime bottlenecks.

# CRITICAL RULES - MUST FOLLOW

## RESPONSES

- Keep responses concise and to the point - unless the user asks otherwise

## PLANNING MODE

- Always ask clarifying questions
- Never assume design, tech stack or features
- Use deep-dive sub-agents to assist with research
- Use deep-dive sub-agents to review the different aspects of your plan before presenting to the user

## CHANGE / EDIT MODE

- Never implement features yourself when possible - use sub-agents!
- Identify changes from the plan that can be implemented in parallel, and use sub-agents to implement the features efficiently
- When using sub-agents to implement features, act as a coordinator only
- Use the best model for the task - premium models for complex tasks (like coding) and mid-tier models for simpler tasks, like documentation
- After completing features (large or small), always run commands like lint, type check and next build to check code quality

## TESTING

- Use any testing tools, libraries available to the project for testing your changes
- Never assume your changes simply work, always test!
- If the project does not have any testing tools, scripts, MCP tools, skills, etc. available for testing, ask the user whether testing should be skipped.

### NEVER

- generate massive monolithic files
- tightly couple modules
- place ML logic inside API routes
- place packet capture logic inside frontend/backend layers
- use blocking operations in async pipelines
- directly couple response engine to iptables (use abstraction layer)

### ALWAYS

- keep packet capture, parsing, session building, feature extraction, ML, threat decision, and response engine as isolated modules
- use queue-based producer-consumer pipeline between capture and processing
- implement ML algorithms manually (NO sklearn classifiers for production logic)
- explain engineering tradeoffs when making architectural decisions

## ML Requirements

- Manual Z-score anomaly detection for traffic spikes, flood detection
- Manual Decision Tree (entropy, information gain, recursive splitting) for attack classification
- Statistical methods preferred over deep learning
- All algorithms must be explainable academically

## Response Engine Design

```
response_engine → firewall abstraction layer → linux/windows/mac adapters
```

Generic methods: `block_ip()`, `unblock_ip()`, `rate_limit_ip()`, `is_blocked()`. Linux-first implementation.

## Developer Learning Context

The developer is a beginner who prefers:

- step-by-step guidance
- concept explanations
- architectural reasoning
- incremental development over massive code dumps

Current priorities: Classes & OOP, Queues, Threading, Networking fundamentals, Dictionaries/lists/sets, Exception handling.

## MVP Priority

1. Packet capture (hybrid thread + queue)
2. Packet parsing
3. Feature extraction
4. Anomaly detection (manual Z-score)
5. WebSocket streaming
6. Dashboard

## FastAPI Structure

`routers/`, `services/`, `schemas/`, `dependencies/`, `websocket/` - keep routes thin, business logic in services.

## Performance Rules

- Packet capture must never block sniffing
- Queue-based architecture between stages
- Minimize DB writes, use aggregation
- Batch expensive operations

## Security

- Never trust packet payloads
- Validate all inputs, sanitize outputs
- Protect WebSocket endpoints
- No unsafe shell execution

## Current Directories

- `packet_capture/` - Scapy sniffers, parsers, packet models
- `traffic_engine/` - Session building
- `feature_engine/` - Feature extraction
- `ml/` - Manual ML implementations
- `threat_engine/` - Threat scoring and classification
- `response_engine/` - Firewal abstraction layer
- `backend/` - FastAPI + WebSocket
- `client/` - React dashboard

## Running the Project

- Backend: `cd backend && python -m uvicorn main:app --reload`
- Frontend: `cd client && npm run dev`
- Packet capture: Run directly from `packet_capture/` module
