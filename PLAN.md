# SmartIDS ML Runtime Correction Plan

## Scope

This plan defines the correction flow for SmartIDS ML development.

The goal is to eliminate training-serving mismatch between the CICIDS2017-trained model and the real-time packet/session pipeline.

Do not modify unrelated frontend, auth, websocket, or UI code unless explicitly required by the ML runtime path.

## Core Problem

The current ML model was trained on CICIDS2017 completed-flow features.

The live project currently extracts only:

```python
protocol
packet_count
total_bytes
duration
avg_packet_size
packet_rate
byte_rate
src_port
dst_port
```

This is not compatible with the trained feature set.

The result is training-serving skew: the model learns from rich offline flow features but receives weak live features during prediction.

This must be corrected before improving accuracy, alerts, UI, or deployment.

## Non-Negotiable Rule

Training features and runtime prediction features must be identical.

One canonical feature schema must be used by:

```text
dataset cleaning
training
evaluation
model saving
runtime prediction
live feature extraction
```

No model should be trained on a feature that cannot be produced by the live packet/session pipeline.

## Target Architecture

```text
packet_capture
-> packet parser
-> flow/session manager
-> short-term flow aggregator
-> live feature extractor
-> early ML detector
-> alert engine
-> optional completed-flow classifier
```

The Scapy sniff callback must remain parse-and-enqueue only. No ML, DB, network calls, file I/O, or expensive aggregation belongs inside `LiveSniffer._handle_packet`.

## Required Build Order

### 1. Create Canonical Feature Schema

Create:

```text
ml/features/schema.py
```

Define:

```python
FEATURE_COLUMNS = [
    "dst_port",
    "protocol",
    "flow_duration",
    "total_fwd_packets",
    "total_fwd_bytes",
    "flow_bytes_per_sec",
    "flow_packets_per_sec",
    "packet_len_min",
    "packet_len_max",
    "packet_len_mean",
    "packet_len_std",
    "packet_len_variance",
    "avg_packet_size",
    "fwd_packet_len_min",
    "fwd_packet_len_max",
    "fwd_packet_len_mean",
    "fwd_packet_len_std",
    "flow_iat_min",
    "flow_iat_max",
    "flow_iat_mean",
    "flow_iat_std",
    "fwd_iat_min",
    "fwd_iat_max",
    "fwd_iat_mean",
    "fwd_iat_std",
    "fwd_iat_total",
    "fwd_packets_per_sec",
    "fin_flag_count",
    "syn_flag_count",
    "rst_flag_count",
    "psh_flag_count",
    "ack_flag_count",
    "urg_flag_count",
    "fwd_header_length",
    "init_win_bytes_forward",
    "act_data_pkt_fwd",
    "min_seg_size_forward",
]

LABEL_COLUMN = "Attack Type"
```

All training and prediction code must import this schema.

Do not duplicate feature lists in multiple files.

### 2. Map CICIDS2017 Columns to Internal Schema

Create:

```text
ml/features/cicids2017_mapping.py
```

Use only live-compatible CICIDS2017 columns.

Mapping:

```python
CICIDS2017_TO_INTERNAL = {
    "Destination Port": "dst_port",
    "Flow Duration": "flow_duration",
    "Total Fwd Packets": "total_fwd_packets",
    "Total Length of Fwd Packets": "total_fwd_bytes",
    "Flow Bytes/s": "flow_bytes_per_sec",
    "Flow Packets/s": "flow_packets_per_sec",
    "Fwd Packet Length Max": "fwd_packet_len_max",
    "Fwd Packet Length Min": "fwd_packet_len_min",
    "Fwd Packet Length Mean": "fwd_packet_len_mean",
    "Fwd Packet Length Std": "fwd_packet_len_std",
    "Min Packet Length": "packet_len_min",
    "Max Packet Length": "packet_len_max",
    "Packet Length Mean": "packet_len_mean",
    "Packet Length Std": "packet_len_std",
    "Packet Length Variance": "packet_len_variance",
    "Average Packet Size": "avg_packet_size",
    "Fwd Packets/s": "fwd_packets_per_sec",
    "FIN Flag Count": "fin_flag_count",
    "PSH Flag Count": "psh_flag_count",
    "ACK Flag Count": "ack_flag_count",
    "Init_Win_bytes_forward": "init_win_bytes_forward",
    "act_data_pkt_fwd": "act_data_pkt_fwd",
    "min_seg_size_forward": "min_seg_size_forward",
}
```

CICIDS2017 does not always include all required live fields directly.

For missing fields, either derive them safely, set default neutral values, or remove them from `FEATURE_COLUMNS`.

Never silently create fake high-signal features.

### 3. Drop Bad Or Unsafe Training Features

Do not train on these for the early real-time model:

```text
Bwd Packet Length Max
Bwd Packet Length Min
Bwd Packet Length Mean
Bwd Packet Length Std
Bwd Header Length
Bwd Packets/s
Bwd IAT Total
Bwd IAT Mean
Bwd IAT Std
Bwd IAT Max
Bwd IAT Min
Active Mean
Active Max
Active Min
Idle Mean
Idle Max
Idle Min
Subflow Fwd Bytes
Init_Win_bytes_backward
```

Reason: these depend on completed bidirectional flows, long observation windows, or reverse-direction stability that the current runtime system does not guarantee.

### 4. Remove `src_port` From ML Features

Do not use `src_port` as a model feature.

Source ports are usually ephemeral and add noise.

Keep `src_port` only as part of the session key:

```python
(src_ip, dst_ip, src_port, dst_port, protocol)
```

The ML feature is:

```python
dst_port
```

### 5. Encode Protocol Correctly

Do not pass raw strings like `TCP`, `UDP`, or `ICMP` into the model.

Use this encoding everywhere:

```python
TCP = 6
UDP = 17
ICMP = 1
UNKNOWN = 0
```

The same encoding must be used in training and runtime.

## Runtime Session Object Requirements

Update the session model so it can calculate live-compatible features.

Required fields:

```python
packet_lengths: list[int]
fwd_packet_lengths: list[int]
packet_timestamps: list[float]
fwd_packet_timestamps: list[float]
packet_count: int
total_bytes: int
fwd_packet_count: int
fwd_total_bytes: int
flag_counts: dict[str, int]
fwd_header_length: int
init_win_bytes_forward: int | None
act_data_pkt_fwd: int
min_seg_size_forward: int | None
src_ip: str
dst_ip: str
src_port: int
dst_port: int
protocol: int
start_time: float
last_seen: float
```

## Runtime Feature Extractor Requirements

Replace the current weak extractor with a full live-compatible extractor.

Required behavior:

```python
class SessionFeatureExtractor:
    def extract(self, session) -> dict:
        ...
```

Rules:

1. Always return every feature in `FEATURE_COLUMNS`.
2. Never return extra features.
3. Never return NaN or infinity.
4. If division by zero occurs, return `0`.
5. If a list has no values, return `0` for min, max, mean, std, and variance.
6. Output column order must match `FEATURE_COLUMNS`.

## Required Helper Functions

Add safe statistical utilities:

```text
feature_engine/stats.py
```

Functions:

```python
safe_min(values) -> float
safe_max(values) -> float
safe_mean(values) -> float
safe_std(values) -> float
safe_variance(values) -> float
safe_rate(value, duration) -> float
safe_iat_stats(timestamps) -> dict
sanitize_feature_dict(features) -> dict
```

All feature extraction must use these helpers.

## Short-Term Flow Aggregation

Do not wait until a flow fully ends before predicting.

Prediction must happen during the session.

Minimum prediction triggers:

```text
session age >= 1 second
or packet_count >= 5
or every N new packets
or every M milliseconds
or on flow end
```

Recommended staged prediction points:

```text
1 second
3 seconds
5 seconds
10 seconds
flow end
```

The session manager must support repeated predictions for the same session.

## Session Expiration Policy

Expire sessions when:

```text
TCP FIN seen
TCP RST seen
idle timeout exceeded
max session duration exceeded
```

Recommended defaults:

```python
IDLE_TIMEOUT_SECONDS = 30
MAX_SESSION_DURATION_SECONDS = 120
```

Do not allow unbounded session memory growth.

## Model Strategy

Use a two-model design.

### Model A: Early Detector

Purpose:

```text
fast real-time detection
partial-flow prediction
low-latency alerts
```

Use only live-compatible short-flow features.

This is the primary runtime model.

### Model B: Completed-Flow Classifier

Purpose:

```text
post-session classification
higher-confidence final labeling
```

This can use richer features later, but only after the flow is complete.

Do not block real-time alerts waiting for Model B.

## Training Pipeline Correction

Create or update:

```text
ml/training/train_cicids2017_live_compatible.py
```

Required flow:

```text
load CICIDS2017
clean column names
map CICIDS2017 columns to internal schema
drop unsupported columns
encode labels
replace inf with 0
fill NaN with 0
select FEATURE_COLUMNS only
split train/test
train model
evaluate
save model
save label encoder
save scaler if used
save feature schema snapshot
```

The saved model artifact must include or be paired with:

```text
model file
label encoder
feature columns
protocol encoding
training timestamp
```

## Evaluation Requirements

Evaluation must report:

```text
accuracy
precision
recall
f1-score
confusion matrix
per-class metrics
false positive rate for Normal Traffic
```

Accuracy alone is not acceptable.

For IDS, false positives matter.

A model with high accuracy but poor attack recall or high normal false positives is not acceptable.

## Data Cleaning Rules

Apply these rules before training:

```python
df = df.replace([float("inf"), float("-inf")], 0)
df = df.fillna(0)
```

Normalize labels consistently:

```text
BENIGN / Normal Traffic -> Normal Traffic
DoS variants -> DoS
DDoS variants -> DDoS
PortScan -> Port Scanning
FTP-Patator / SSH-Patator -> Brute Force
Web Attack variants -> Web Attacks
Bot -> Bots
```

Keep label mapping centralized.

## Do Not Overbuild

Do not build deep learning models yet.

Do not build complex dashboards yet.

Do not optimize UI before fixing runtime ML correctness.

Do not add backward-flow features until bidirectional flow tracking is reliable.

Do not chase maximum CICIDS2017 benchmark accuracy if the feature set cannot be reproduced live.

## Acceptance Criteria

The correction is complete only when all conditions are true:

```text
1. Training uses only FEATURE_COLUMNS.
2. Runtime extractor outputs exactly FEATURE_COLUMNS.
3. Model prediction accepts live session features without missing columns.
4. No NaN/inf reaches the model.
5. src_port is not used as an ML feature.
6. protocol is numerically encoded.
7. Session manager supports repeated prediction before flow end.
8. Session expiration prevents memory leaks.
9. Evaluation reports per-class metrics, not only accuracy.
10. Early detector can generate alerts from partial flows.
```

## Priority Execution Plan

### Phase 1: Feature Contract

```text
create ml/features/schema.py
create ml/features/cicids2017_mapping.py
centralize label mapping
remove duplicated feature lists
```

### Phase 2: Dataset Pipeline

```text
clean CICIDS2017
map columns
drop unsupported features
train live-compatible model
save model artifacts
evaluate with per-class metrics
```

### Phase 3: Runtime Extractor

```text
expand Session object
track packet lengths
track timestamps
track TCP flags
track TCP window size
track header lengths
calculate IAT stats
return exact FEATURE_COLUMNS
```

### Phase 4: Flow Manager

```text
maintain session table
update session per packet
run prediction during active session
expire sessions safely
run final prediction on flow end
```

### Phase 5: Alert Integration

```text
send early model result to alert engine
threshold confidence
avoid duplicate alerts for same session
update alert if final model changes classification
```

## Final Constraint

The system must be designed around this principle:

```text
Train only on what the live system can honestly observe.
```

Anything else produces fake accuracy and unreliable real-time IDS behavior.
