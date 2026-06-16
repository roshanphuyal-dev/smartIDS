# Linux Test Lab Plan

Purpose: validate SmartIDS behavior in a disposable Linux VM without exposing the host or any shared network.

## Goals

- Measure detection and alert quality in a controlled environment.
- Verify reactive mitigation only affects future traffic.
- Keep every test reproducible and easy to reset.

## Lab Rules

- Use one disposable Linux VM only.
- No production data.
- No bridge to a shared or public network.
- Prefer host-only or isolated virtual networking.
- Take snapshots before each test phase.

## Test Surface

- Packet replay into the VM.
- IDS capture and queue processing.
- Session/flow aggregation.
- Alert generation and backend reporting.
- Response actions against future traffic only.

## Phases

1. Baseline
- Boot a clean VM snapshot.
- Confirm network isolation.
- Start SmartIDS services.
- Capture a no-attack baseline.

2. Replay
- Feed known benign traffic.
- Feed known suspicious traffic.
- Record detections, timing, and false positives.

3. Response
- Trigger a small set of block/watchlist actions.
- Verify only future traffic is affected.
- Confirm the host stays reachable.

4. Cleanup
- Stop services.
- Revert the VM snapshot.
- Archive only sanitized results.

## Success Criteria

- The lab can be recreated from scratch.
- The host remains isolated from the test VM.
- Results are comparable across runs.
- No test step requires production connectivity.

## Notes

- Keep the lab intentionally simple.
- Prefer repeatability over scale.
- Expand only after the basic isolation and replay flow works.
