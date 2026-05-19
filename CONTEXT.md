# SmartIDS Agent Instructions

==================================================
PROJECT IDENTITY
==================================================

Project Type:
Realtime AI-assisted Intrusion Detection and Reactive Response System (IDS/IPS)

IMPORTANT:
This is NOT a kernel-level inline IPS.

The system uses passive packet sniffing with Scapy.
Packets are observed as copies after entering the OS networking stack.

Therefore:
- malicious packets may already reach applications before detection
- response engine blocks FUTURE traffic only
- system performs reactive mitigation, not perfect prevention

Correct project positioning:
“Realtime AI-assisted IDS with automated reactive mitigation.”

==================================================
CORE ARCHITECTURE
==================================================

Packet Capture
    ↓
Packet Parsing
    ↓
Traffic Session Building
    ↓
Feature Extraction
    ↓
ML Detection Engine
    ↓
Threat Decision Engine
    ↓
Response Engine
    ↓
FastAPI + WebSocket Streaming
    ↓
Realtime Dashboard

==================================================
HYBRID PACKET CAPTURE ARCHITECTURE
==================================================

FINAL DECISION:
Hybrid Thread + Queue + AsyncIO Architecture

Structure:
- Dedicated thread for Scapy packet sniffing
- Queue-based buffering between capture and processing
- AsyncIO consumers for downstream processing

Reasoning:
Scapy is blocking internally and not truly async-native.

Capture thread responsibilities:
- sniff packet
- minimally parse
- enqueue packet
- return immediately

Processing responsibilities:
- packet parsing
- session aggregation
- feature extraction
- ML inference
- logging
- websocket broadcasting

IMPORTANT RULE:
Packet capture must NEVER block.

==================================================
CRITICAL ENGINEERING RULES
==================================================

NEVER:
- generate massive monolithic files
- tightly couple modules
- place ML logic inside API routes
- place packet capture logic inside frontend/backend layers
- use blocking operations inside async pipelines
- directly couple response engine to iptables
- overengineer UI before backend stability
- use sklearn classifiers for final ML logic

ALWAYS:
- separate capture, parsing, session building, ML, threat scoring, and response handling into isolated modules
- use queue-based producer-consumer pipelines
- keep APIs thin and business logic modular
- explain engineering tradeoffs when making decisions
- prioritize throughput and packet safety over flashy features
- design for scalability and maintainability

==================================================
PROJECT GOALS
==================================================

Primary goals:
- realtime packet monitoring
- session-aware traffic analysis
- custom feature extraction
- explainable ML detection
- automated reactive mitigation
- realtime dashboard visualization
- scalable backend architecture

Secondary goals:
- portfolio-quality architecture
- backend engineering showcase
- cybersecurity showcase
- realtime systems showcase

==================================================
ML REQUIREMENTS
==================================================

IMPORTANT:
Do NOT use sklearn classifiers for production logic.

ML must be manually implemented for academic explainability.

Model 1:
Statistical Anomaly Detection
- manual Z-score implementation
- moving averages
- standard deviation
- anomaly thresholds

Detects:
- traffic spikes
- flooding
- abnormal packet rates
- scanning behavior

Model 2:
Manual Decision Tree Classifier

Implement manually:
- entropy
- information gain
- recursive splitting
- leaf classification
- tree traversal

Detects:
- SYN flood
- brute force behavior
- suspicious traffic patterns
- port scanning

Statistical and explainable methods are preferred over deep learning.

==================================================
RESPONSE ENGINE DESIGN
==================================================

IMPORTANT:
Use firewall abstraction layer.

Correct structure:

response_engine
    ↓
firewall abstraction layer
    ↓
linux adapter
windows adapter
mac adapter

Generic methods:
- block_ip()
- unblock_ip()
- rate_limit_ip()
- is_blocked()

Linux-first implementation is acceptable initially.

==================================================
PERFORMANCE RULES
==================================================

Primary focus:
- sustained throughput
- queue buffering
- packet loss minimization
- realtime responsiveness

IMPORTANT:
Packet streams can become massive.

Avoid:
Packet → DB writes directly

Preferred flow:
Packet → Queue → Aggregation → ML → DB

Rules:
- minimize blocking operations
- batch expensive operations
- aggregate before persistence
- isolate ML from capture layer
- reduce unnecessary logging

==================================================
SECURITY RULES
==================================================

- never trust packet payloads
- validate and sanitize all inputs
- protect websocket endpoints
- avoid unsafe shell execution
- isolate firewall command execution
- prevent parser crashes from malformed packets

==================================================
FASTAPI BACKEND STRUCTURE
==================================================

Recommended structure:
- routers/
- services/
- schemas/
- dependencies/
- websocket/

IMPORTANT:
Keep routes thin.
Business logic belongs in services/modules.

==================================================
CURRENT PROJECT STRUCTURE
==================================================

packet_capture/
- sniffers/
- parsers/
- packet_models/
- utils/
- tests/

traffic_engine/
- session building
- aggregation
- flow tracking

feature_engine/
- feature extraction
- transformations
- feature storage

ml/
- anomaly detection
- decision tree
- training
- inference

threat_engine/
- threat scoring
- classification
- alert management

response_engine/
- firewall abstraction
- blacklist management
- rate limiting

backend/
- FastAPI
- WebSockets
- APIs
- auth

client/
- React dashboard
- realtime visualization

==================================================
MVP PRIORITY ORDER
==================================================

1. Packet capture (thread + queue)
2. Packet parsing
3. Traffic/session aggregation
4. Feature extraction
5. Z-score anomaly detection
6. Threat scoring
7. WebSocket streaming
8. Dashboard visualization
9. Decision tree classifier
10. Reactive blocking
11. Database integration
12. Optimization & deployment

==================================================
DEVELOPER LEARNING CONTEXT
==================================================

Developer is a beginner and prefers:
- step-by-step guidance
- concept explanations
- architectural reasoning
- incremental development
- learning-focused mentoring

Avoid:
- giant code dumps
- overcomplicated abstractions
- unnecessary advanced networking internals
- excessive optimization too early

Current learning priorities:
1. Classes & OOP
2. Queues
3. Threading
4. Networking fundamentals
5. Dictionaries/lists/sets
6. Exception handling

Later topics:
- AsyncIO
- Dataclasses
- Logging
- Type hints
- Time-window statistics
- Performance optimization

==================================================
PROJECT PHILOSOPHY
==================================================

Architecture quality is more important than:
- flashy UI
- advanced neural networks
- excessive features
- “hacker-style” visuals

The system should prioritize:
- clean modular design
- realtime stability
- explainable detection
- operational clarity
- maintainable engineering