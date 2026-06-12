# SmartIDS Project Context

## Project Identity

SmartIDS is a realtime AI-assisted intrusion detection system with automated reactive mitigation.

It is not a kernel-level inline IPS. Scapy passively sniffs packet copies after packets enter the OS networking stack. Malicious packets may already reach applications before detection. The response engine can block or rate-limit future traffic only.

Correct positioning: realtime AI-assisted IDS with reactive mitigation.

## Current Correction Focus

The most important current work is eliminating ML training-serving mismatch.

The existing CICIDS2017-trained model uses completed-flow features, while the live runtime currently produces only a small weak feature set. This causes feature shape mismatches, fake benchmark confidence, and unreliable live predictions.

The system must follow this rule:

```text
Train only on what the live system can honestly observe.
```

Training features and runtime prediction features must be identical.

## Target Runtime Architecture

```text
packet_capture
-> packet parser
-> flow/session manager
-> short-term flow aggregator
-> live feature extractor
-> early ML detector
-> alert engine
-> optional completed-flow classifier
-> response engine
-> backend/websocket/dashboard
```

## Capture Architecture

SmartIDS uses a hybrid thread plus queue architecture.

Scapy is blocking internally and not async-native, so live sniffing runs in a dedicated thread. The sniff callback must parse minimally, enqueue packet data, and return immediately.

Processing work happens outside the sniff callback:

```text
session aggregation
feature extraction
ML inference
alert generation
logging
websocket broadcasting
persistence
response handling
```

Packet capture must never block on ML, DB, network, file I/O, or long-running computations.

## ML Runtime Requirements

One canonical feature schema must be used by:

```text
dataset cleaning
training
evaluation
model saving
runtime prediction
live feature extraction
```

The canonical schema belongs in `ml/features/schema.py`.

All training and runtime code must import `FEATURE_COLUMNS`; no duplicated feature lists.

Protocol encoding must be identical in training and runtime:

```python
TCP = 6
UDP = 17
ICMP = 1
UNKNOWN = 0
```

`src_port` must not be an ML feature. It is allowed only in the session key. The model may use `dst_port`.

No NaN or infinity may reach the model.

## Model Strategy

Use a two-model strategy.

Model A is the early detector. It runs during active sessions, uses only live-compatible short-flow features, and is the primary runtime model.

Model B is a completed-flow classifier. It can use richer features later, but only after a flow is complete. It must not block real-time alerts.

Deep learning and complex benchmark chasing are out of scope until runtime correctness is fixed.

## CICIDS2017 Training Rules

CICIDS2017 columns must be mapped through `ml/features/cicids2017_mapping.py`.

Use only live-compatible columns for the early detector.

Do not train the early detector on completed-flow backward features, unstable reverse-direction features, active/idle long-window features, or any field the live system cannot currently compute.

Centralize label normalization. Evaluation must include accuracy, precision, recall, F1, confusion matrix, per-class metrics, and false positive rate for Normal Traffic.

## Runtime Session Requirements

The runtime session object must track enough information to produce the canonical schema:

```text
packet lengths
forward packet lengths
packet timestamps
forward packet timestamps
packet and byte counters
forward packet and byte counters
TCP flag counts
forward header length
initial forward TCP window bytes
active forward data packet count
minimum forward segment size
source and destination endpoints
numeric protocol
start time
last seen time
```

Feature extraction must use safe helpers for min, max, mean, std, variance, rates, IAT stats, and sanitization.

If a value cannot be computed safely, use neutral `0`.

## Short-Term Flow Aggregation

Do not wait for full flow completion before predicting.

Prediction should happen during the session at staged points such as 1 second, 3 seconds, 5 seconds, 10 seconds, and flow end.

Minimum triggers include session age >= 1 second, packet_count >= 5, periodic packet/time windows, and flow end.

The session manager must support repeated predictions for the same session.

## Session Expiration

Expire sessions when TCP FIN is seen, TCP RST is seen, idle timeout is exceeded, or max session duration is exceeded.

Recommended defaults:

```python
IDLE_TIMEOUT_SECONDS = 30
MAX_SESSION_DURATION_SECONDS = 120
```

Session memory must be bounded.

## Response Engine Direction

Use a firewall abstraction layer. Do not directly couple response logic to one platform command.

Expected shape:

```text
response_engine
-> firewall abstraction layer
-> linux adapter
-> windows adapter
-> mac adapter
```

Generic methods:

```text
block_ip()
unblock_ip()
rate_limit_ip()
is_blocked()
```

Linux-first implementation is acceptable initially.

## Performance Rules

Prioritize sustained throughput, queue buffering, packet loss minimization, and realtime responsiveness.

Avoid direct packet-to-database writes.

Preferred flow:

```text
Packet -> Queue -> Aggregation -> ML -> Alert -> Optional Persistence
```

Reduce unnecessary logging in hot paths. Batch expensive operations where possible.

## Security Rules

Never trust packet payloads.

Validate and sanitize all inputs.

Prevent parser crashes from malformed packets.

Protect websocket endpoints when backend work is introduced.

Avoid unsafe shell execution.

Isolate firewall command execution behind adapters.

## Current Directory Roles

```text
packet_capture/   Scapy sniffers, parsers, packet models, capture orchestration
traffic_engine/   Session and flow management
feature_engine/   Runtime feature extraction and safe stats helpers
ml/               Models, dataset loaders, training, evaluation, schema, mappings
threat_engine/    Threat scoring and alert decisions
response_engine/  Reactive mitigation and firewall abstraction
backend/          Future API and websocket layer
client/           Future dashboard
tests/            Future automated verification
```

## Development Priorities

1. Create the canonical ML feature contract.
2. Correct the CICIDS2017 dataset pipeline to train only on live-compatible features.
3. Expand runtime session tracking to produce the canonical feature set.
4. Replace the weak runtime extractor with exact-schema extraction.
5. Add short-term flow aggregation and repeated active-session prediction.
6. Add safe session expiration and memory bounds.
7. Integrate early ML alerts.
8. Add completed-flow classification later only after early detection works.

## Non-Goals Until Runtime ML Is Correct

Do not build deep learning models.

Do not build complex dashboards.

Do not optimize UI.

Do not add backward-flow-heavy features until bidirectional tracking is reliable.

Do not chase maximum CICIDS2017 benchmark accuracy if the live system cannot reproduce the features.

## Developer Learning Context

Prefer incremental development, clear architecture, and short explanations of tradeoffs.

Avoid giant code dumps and unnecessary advanced abstractions.

Current learning priorities include classes and OOP, queues, threading, networking fundamentals, dictionaries, lists, sets, and exception handling.
