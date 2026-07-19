# SmartIDS Agent Notes

## Project Identity

- SmartIDS is a passive, userland IDS with automated reactive mitigation.
- It is not a kernel-level inline IPS.
- Scapy observes packet copies after the OS networking stack, so mitigation can only block future traffic.
- Do not describe the system as perfect prevention or inline packet blocking.

## Current Priority

- The active project goal is safe IDS background engine implementation without disrupting current IDS capture or existing ML model artifacts.
- Preserve the current working IDS process while adding small, opt-in engine components around it.
- Continue protecting the ML runtime contract: training features and runtime prediction features must stay identical.
- Reference `PLAN.md` for the execution plan and `CONTEXT.md` for architecture constraints.
- Record every planned, active, and completed implementation step in `backend/CHECKLIST.md` before and after code changes.

## Scope Control

- Do not modify frontend, auth, websocket, UI, or unrelated backend code unless required by the ML runtime path.
- Do not overbuild dashboards, deep learning models, or completed-flow classifiers before the early live-compatible detector works.
- Prefer small, verifiable changes over large rewrites.
- Keep implementations short and focused. Complete one safe increment, verify it, update `backend/CHECKLIST.md`, then suggest exactly one next implementation step.
- Major database, API contract, project-plan, or model changes must be explicitly logged in `backend/CHECKLIST.md` under the major change log.

## Next IDS Engine Implementation

- Build the background engine in safe increments around the existing flow: capture -> queue -> session builder -> feature extractor -> heuristic/ML detection -> response policy/blocker -> backend reporter.
- Do not replace the current packet processor or model loading path unless a later verified step requires it.
- Prefer additive, opt-in integrations controlled by environment variables or new small modules.
- First implementation focus: backend reporting contracts for session-level IDS events and alerts, without changing model files or retraining.

## Capture Architecture Constraint

- `scapy.sniff(...)` is blocking and runs in a dedicated thread.
- `LiveSniffer._handle_packet` must stay minimal: parse + enqueue only.
- Never add ML inference, database writes, network calls, file I/O, heavy aggregation, or blocking work in the sniff callback.

## ML Runtime Contract

- Create one canonical schema in `ml/features/schema.py`.
- All dataset cleaning, training, evaluation, model saving, runtime prediction, and live extraction must import the same `FEATURE_COLUMNS`.
- Never duplicate feature lists across files.
- Never train on a feature that the live packet/session pipeline cannot honestly produce.
- `src_port` must not be an ML feature; keep it only in the session key.
- `dst_port` is allowed as an ML feature.
- Protocol must be numeric everywhere: TCP=6, UDP=17, ICMP=1, UNKNOWN=0.
- No NaN or infinity may reach the model.

## CICIDS2017 Rules

- Map CICIDS2017 columns through `ml/features/cicids2017_mapping.py`.
- Use only live-compatible columns for the early detector.
- Drop completed-flow or unstable backward-flow features until bidirectional runtime tracking is reliable.
- Centralize label normalization.
- Evaluation must include per-class metrics, confusion matrix, and false positive rate for Normal Traffic.

## Runtime Feature Extraction

- Expand the session model to track packet lengths, forward packet lengths, timestamps, forward timestamps, counters, TCP flags, forward header length, initial forward window bytes, active forward data packet count, and minimum forward segment size.
- `SessionFeatureExtractor.extract(session)` must return exactly `FEATURE_COLUMNS` with no extras and no missing fields.
- Use safe stats helpers from `feature_engine/stats.py` for min, max, mean, std, variance, rates, IAT stats, and sanitization.
- If a value cannot be computed safely, use a neutral `0` rather than NaN or infinity.

## Flow Prediction Rules

- Do not wait for full flow completion before prediction.
- Support repeated prediction during an active session.
- Minimum triggers: age >= 1 second, packet_count >= 5, periodic packet/time windows, and flow end.
- Expire sessions on FIN, RST, idle timeout, or max duration.
- Recommended defaults: idle timeout 30 seconds, max duration 120 seconds.
- Prevent unbounded session memory growth.

## Primary Commands

- Packet capture: `sudo .venv/bin/python -m packet_capture.main`
- Train legacy CICIDS model: `python3 -m ml.training.train_cicids2017`
- Evaluate legacy CICIDS model: `python3 -m ml.evaluation.evaluate_cicids2017`
- Future live-compatible training: `python3 -m ml.training.train_cicids2017_live_compatible`

## Dependencies

- Python dependencies are tracked in `requirements.txt`.
- Windows-specific dependencies are tracked in `requirements_windows.txt`.
- After dependency changes, update the relevant requirements file from the active environment.

## Known Footguns

- Keep import paths aligned with actual folders.
- Keep packet model types aligned with parser output.
- Avoid printing in hot packet-processing paths except rate-limited debug output.
- Be careful with file mode-only git diffs on Windows/WSL.

## Engineering Style

- Keep modules isolated: capture, parsing, session/flow management, feature extraction, ML, alerting, and response handling.
- Keep APIs thin; business logic belongs in services/modules.
- Use queue-based producer-consumer boundaries where packet throughput matters.
- Validate changes with compile/tests or targeted smoke checks when possible.

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.
