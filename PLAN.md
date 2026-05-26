# SmartIDS Flow-Based IDS Redesign Plan

## Problem Statement

SmartIDS has a major architectural mismatch:

1. ML training (CICIDS2017) uses 70-80 engineered flow/session-level features.
2. Runtime live pipeline currently extracts only a handful of packet-level fields.

This causes inference failures (feature shape mismatch) and/or unreliable predictions.

Correct solution: move runtime to short-window flow/session aggregation and retrain ML on only runtime-computable features with a strict, persisted schema shared by training and inference.

## Target Runtime Architecture

incoming packets
-> Stage 1 packet heuristics (ultra-fast)
-> flow/session tracker (bidirectional, TTL, memory-bounded)
-> incremental flow feature updates
-> short aggregation window (time: 1-3s, packet-count: 5-20 packets)
-> feature alignment (exact schema/order, defaults, validation)
-> XGBoost prediction (binary: benign vs attack)
-> alert generation (merge Stage 1 + Stage 2 signals)

Non-negotiable: `LiveSniffer._handle_packet` must remain parse + enqueue only (no I/O, ML, disk, network).

## Decisions Locked In

1. Forward direction: packet-heuristic-forward (client->server inference).
2. Protocol encoding: explicit mapping TCP=6, UDP=17, ICMP=1, UNKNOWN=0.
3. Production labels: binary only for now (benign vs attack).
4. Forward heuristic policy: service-port heuristic:
   - infer server using well-known/privileged port rules, fallback to first-packet-forward if ambiguous.

## Repo Reality (Verified)

1. Capture: `packet_capture/` queue-based pipeline (`SnifferService` + `LiveSniffer`).
2. Current session tracking exists: `traffic_engine/session_builder/SessionBuilder` + `TrafficSession` (directional today).
3. Current feature extraction exists but minimal: `feature_engine/extractors/session_feature_extractor.py`.
4. Training pipeline exists: `ml/training/train_cicids2017.py` + `CICIDS2017Loader` + `DatasetLoader`.

## Phase 0: Define the Runtime Feature Contract (First Deliverable)

Goal: a single feature schema used by both training and runtime, with strict alignment.

Deliverables:
1. `feature_engine/schema/runtime_feature_schema.json`
   - ordered list of feature names.
2. `feature_engine/schema/feature_defaults.json`
   - default values for any missing features at runtime.
3. A loader utility that returns the ordered schema list for both runtime and training.

Rules:
1. Runtime feature dicts MUST be alignable into the exact ordered schema.
2. Training MUST select and rename dataset columns to match schema keys exactly.
3. Inference MUST validate vector length/order and fail fast if schema mismatches.

Initial schema (v1, runtime-computable):
1. flow_duration
2. total_fwd_packets
3. total_bwd_packets
4. total_fwd_bytes
5. total_bwd_bytes
6. flow_bytes_per_sec
7. flow_packets_per_sec
8. average_packet_size
9. packet_length_std
10. inter_arrival_time_mean
11. syn_flag_count
12. ack_flag_count
13. rst_flag_count
14. psh_flag_count
15. active_time_mean
16. idle_time_mean
17. destination_port
18. protocol

Notes:
1. Feature set intentionally smaller than CICFlowMeter to keep runtime feasible.
2. Defaults must be deterministic (typically 0) to prevent runtime crashes early in flows.

## Phase 1: Upgrade Packet Parsing (Minimal, Runtime Needed Only)

Goal: parse only what Stage 1 and flow aggregation require.

Changes:
1. `packet_capture/packet_models/packet_data.py`
   - add TCP flag info (at minimum SYN/ACK/RST/PSH boolean or a bitmask).
   - keep protocol as string if desired, but also provide numeric id via mapping at feature time.
2. `packet_capture/parsers/packet_parser.py`
   - extract TCP flags when TCP exists.
   - keep packet_size and timestamp consistent (prefer `time.time()` already used).

Constraints:
1. No heavy computation in sniff callback.
2. No prints in hot paths except rate-limited debug mode.

## Phase 2: Implement Bidirectional Flow Tracking (Core Runtime Change)

Problem today:
1. Current `SessionKey` is directional (src->dst), which breaks fwd/bwd stats.

Deliverables:
1. `traffic_engine/flow_tracker/flow_key.py`
   - bidirectional canonical key for 5-tuple:
     - endpoints A=(ip,port), B=(ip,port), protocol
     - order endpoints deterministically (sorted tuple)
2. `traffic_engine/flow_tracker/flow_state.py`
   - per-flow rolling stats + metadata:
     - start_ts, last_ts
     - counters: fwd/bwd packets, fwd/bwd bytes
     - ring buffers or online accumulators for:
       - packet sizes (std)
       - IAT deltas (mean)
     - TCP flag counters (syn/ack/rst/psh)
     - active/idle segmentation accumulators
     - client_endpoint and server_endpoint (from heuristic)
3. `traffic_engine/flow_tracker/flow_tracker.py`
   - `update(packet) -> FlowWindowSnapshot | None`
   - responsibilities:
     - determine flow key
     - determine packet direction fwd/bwd (client->server vs server->client)
     - update flow state
     - emit window snapshots by:
       - time window (e.g. every 2s per flow)
       - packet-count window (e.g. every 10 packets)
     - evict flows by idle TTL + memory bounds (LRU)

Forward Direction Heuristic (service-port policy):
1. Determine endpoints from first seen packet:
   - endpoint1=(src_ip,src_port), endpoint2=(dst_ip,dst_port)
2. Choose server endpoint:
   - if one port is in a well-known list (80,443,22,53,123,445,3389,139,143,110,25,587,993,995,3306,5432,6379,27017, etc), that endpoint is server.
   - else if one port <=1024 and other >1024, <=1024 is server.
   - else ambiguous: fallback to first-packet-forward (src is client, dst is server).
3. Once set, do not change direction for that flow.

## Phase 3: Flow Window Feature Extraction (Incremental, Runtime-Compatible)

Deliverables:
1. `feature_engine/extractors/flow_feature_extractor.py`
   - input: FlowWindowSnapshot/FlowState
   - output: dict matching runtime schema keys exactly

Computations (v1):
1. flow_duration = last_ts - start_ts (guard >=0)
2. total_fwd_packets / total_bwd_packets
3. total_fwd_bytes / total_bwd_bytes
4. flow_bytes_per_sec = total_bytes / duration (guard duration>0)
5. flow_packets_per_sec = total_packets / duration (guard duration>0)
6. average_packet_size = total_bytes / total_packets (guard total_packets>0)
7. packet_length_std = std over packet sizes in window (online Welford preferred)
8. inter_arrival_time_mean = mean IAT (online mean)
9. syn/ack/rst/psh counts from packet flags
10. active_time_mean / idle_time_mean via gap thresholding:
   - ACTIVE_GAP (e.g. 1.0s) defines whether a gap is active continuation vs idle gap
11. destination_port = server port (chosen from heuristic)
12. protocol = numeric id (TCP=6, UDP=17, ICMP=1, UNKNOWN=0)

## Phase 4: Stage 1 Packet-Level Heuristics (Immediate Response)

Deliverables:
1. `detection_engine/heuristics/heuristic_engine.py`
2. `detection_engine/heuristics/state.py` (TTL counters, rolling windows)
3. `detection_engine/heuristics/rules.py` (pure rule functions)

Rules to implement (v1):
1. SYN flood suspicion:
   - SYN rate to (dst_ip,dst_port) over last 1s
   - SYN/ACK imbalance per dst
2. Port scan suspicion:
   - unique dst_port count contacted by src_ip over last T seconds
3. Abnormal packet rate / bursts:
   - packets/sec and bytes/sec per src_ip (sliding window or token bucket)
4. Suspicious flag combos:
   - NULL flags, Xmas tree, SYN+FIN, etc
5. Malformed/odd traffic:
   - missing ports where expected, invalid lengths (best-effort)

Output:
1. `HeuristicResult`: severity score + list of rule hits + minimal context.

Performance:
1. Must stay microsecond/millisecond class and run in the consumer thread, never in sniff callback.

## Phase 5: Redesign ML Training to Match Runtime (Critical)

Goal: train ONLY on runtime schema features and persist artifacts needed for alignment.

Deliverables:
1. Dataset column mapping for CICIDS2017 -> runtime schema keys (explicit dict).
2. Updated loader/training pipeline:
   - clean malformed rows
   - remove NaN/inf robustly
   - normalize labels
   - remove constants/useless columns
   - remove duplicates
   - select only runtime features
   - stratified 80/20 split
   - persist:
     - model
     - label encoder
     - feature schema (must match runtime schema exactly)
     - schema hash/version metadata

Preprocessing improvements:
1. Replace inf with NaN.
2. Prefer imputation (median) rather than dropping all NaN rows, to preserve data volume.
3. Enforce required feature columns presence; fail training if missing.
4. Cast numeric dtypes to reduce memory (float32 where safe).

Model strategy:
1. Production runtime uses only XGBoostClassifier.
2. Multiple models only for benchmarking/training.

## Phase 6: Runtime Prediction Pipeline (Low Latency, Strict Alignment)

Deliverables:
1. `runtime/model_loader.py`
   - loads XGBoost model, label encoder, schema + schema hash
2. `runtime/feature_aligner.py`
   - dict -> ordered vector
   - apply defaults for missing keys
   - optionally reject unknown keys
   - validate length/order against schema
3. `runtime/predictor.py`
   - uses `predict_proba`, applies thresholding
4. `runtime/pipeline.py`
   - orchestrates:
     - packet -> heuristics -> flow_tracker -> window -> feature extraction -> alignment -> ML -> alert

Queueing / threading:
1. sniff thread: parse + enqueue only
2. consumer thread: heuristics + flow tracking
3. ML inference thread (optional but recommended): consumes window snapshots; keeps inference off the main consumer hot loop

Backpressure:
1. bounded queues
2. if full: drop newest or oldest deterministically; increment counters; never block sniff callback.

## Phase 7: Integrate Into Existing PacketProcessor

Current `PacketProcessor` prints session features per packet.

Target:
1. `PacketProcessor` becomes the orchestrator:
   - run Stage 1 heuristics on each packet
   - update flow tracker
   - on window emission:
     - extract aligned flow features
     - run ML inference
     - output a single alert record

Replace `print` spam with:
1. structured logging
2. rate-limited debug output
3. alert-only output by default

## Phase 8: Custom Decision Tree (Academic / Benchmark Only)

Deliverables:
1. `ml/models/custom_decision_tree.py`
   - `fit()`, `predict()`
   - gini impurity
   - recursive splitting
   - max_depth
   - multiclass support
2. Use only for benchmarking/training comparisons, not runtime.

Future optional:
1. custom Random Forest built atop the custom Decision Tree (after DT is stable).

## Phase 9: Tests and Verification (Before Expanding Features)

Unit tests:
1. Flow key canonicalization (direction-independent key).
2. Forward heuristic correctness (service-port rules + fallback).
3. Window emission (time + packet windows).
4. Feature correctness on synthetic packet sequences.
5. Feature alignment schema enforcement.
6. Training/inference parity: the saved `feature_columns.json` must equal runtime schema.

Smoke tests:
1. Train model on runtime feature subset.
2. Load model + schema and run prediction on synthetic flow vectors.
3. Live run: `sudo .venv/bin/python -m packet_capture.main`:
   - no crashes
   - windows emit
   - alerts produced

## Recommended Execution Order (Concrete)

1. Phase 0 schema contract
2. Phase 2 flow tracker skeleton + TTL + window emission
3. Phase 3 flow feature extractor for schema
4. Phase 5 retrain XGBoost on schema-only features (persist artifacts)
5. Phase 6 runtime loader + aligner + predictor
6. Phase 4 heuristics engine and integrate
7. Phase 7 integrate into PacketProcessor end-to-end
8. Phase 9 tests
9. Phase 8 custom decision tree + benchmarks
10. iterate: feature expansion only after v1 stability

## Default Config (v1)

1. flow idle timeout: 30s
2. window interval: 2s
3. packet window: 10 packets
4. ACTIVE_GAP: 1.0s
5. max flows: 50k (tune)
6. queues:
   - packet_queue: 10000 (existing)
   - flow_window_queue: 5000
   - alert_queue: 5000
7. ML decision threshold: 0.5 (configurable)

## Alert Format (Single Unified Output)

1. timestamp
2. flow_key (canonical endpoints + protocol)
3. stage1:
   - severity score
   - rule hits
4. stage2:
   - predicted_label
   - probability
   - model version / schema hash
5. optional: flow feature snapshot (debug flag)

## Non-Goals (This Iteration)

1. Full 70-80 CICIDS features at runtime.
2. Waiting for long sessions to complete before detection.
3. Inline IPS blocking (userland IDS with reactive mitigation only).
