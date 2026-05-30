# IDS Background Engine Plan

Build a safe, opt-in IDS background engine around the current working IDS runtime. The engine owns packet observation, session tracking, feature extraction, heuristic detection, ML prediction, response decisions, and backend reporting. The FastAPI backend remains the API, storage, and frontend communication layer.

## Guardrails

- Preserve the current packet capture flow and existing ML model artifacts.
- Keep `LiveSniffer._handle_packet` minimal: parse packets and enqueue them only.
- Do not run ML inference, database writes, network calls, file I/O, heavy aggregation, or blocking work inside the sniff callback.
- Add engine pieces in small, verified increments controlled by explicit environment variables where possible.
- Keep SmartIDS as a passive userland IDS with reactive mitigation; blocking can only affect future traffic after detection.

## Engine Pipeline

```text
capture -> queue -> session builder -> feature extractor -> heuristic/ML detection -> response policy/blocker -> backend reporter
```

## Responsibilities

- Packet capture: parse source IP, destination IP, source port, destination port, numeric protocol, timestamp, packet size, and TCP flags.
- Session building: group packets by source IP, destination IP, source port, destination port, and protocol before backend reporting.
- Session state: maintain session ID, start time, last seen, duration, packet count, byte count, forward/backward counters, packets/sec, and bytes/sec.
- Feature extraction: use the canonical ML feature schema and never send NaN or infinity to the model.
- Heuristic detection: detect port scanning, brute force patterns, repeated suspicious attempts, SYN flood behavior, high request rate, repeated connections, and known blocked/watchlisted IP activity.
- ML detection: run prediction on session-level features and produce prediction, attack type, confidence score, and risk score.
- Blocking: support automatic block, manual block, unblock, and watchlist commands through environment-specific blockers.
- Backend reporting: send normalized alerts, session updates, block events, and blocked/watchlisted IP activity summaries.

## Backend Alert Payload

- `threat_id`
- `timestamp`
- `source_ip`
- `source_port`
- `destination_ip`
- `destination_port`
- `protocol`
- `attack_type`
- `severity`
- `confidence_score`
- `detection_method`
- `action_taken`
- `session_id`

## Backend Session Update Payload

- `session_id`
- `timestamp`
- `source_ip`
- `destination_ip`
- `source_port`
- `destination_port`
- `protocol`
- `duration`
- `packet_count`
- `byte_count`
- `session_state`
- `risk_score`
- `ml_prediction`
- `heuristic_result`

## Implementation Order

1. Add opt-in backend IDS event reporting for session-level ML prediction events.
2. Add controlled session update reporting at prediction and session-expiration points.
3. Normalize heuristic outputs into the same reporting contract.
4. Add blocked/watchlisted IP activity tracking.
5. Add backend command polling or streaming for manual block, unblock, and watchlist operations.
6. Verify each increment with compile checks, focused smoke tests, or controlled live-capture tests.

## Existing Follow-Up Items

- Model B is not implemented yet: the completed-flow classifier phase remains optional later work.
- Alert deduplication and update logic still needs a robust design to avoid duplicate alerts for the same session and update final classification cleanly.
- Strict single-source schema validation is still needed to ensure all training, evaluation, model saving, runtime prediction, and live extraction paths import one schema and mapping source.
