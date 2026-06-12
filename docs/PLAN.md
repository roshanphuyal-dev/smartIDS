# SmartIDS Master Plan

## Current Priority Order

1. Merge frontend and backend persistence onto one database and move shared database artifacts under `/database`.
2. Build an isolated Linux test-lab plan for safe validation against a deliberately vulnerable VM.
3. Revamp the frontend around raw IDS event inspection and clearer live data display.
4. Add the custom decision tree model after the database and lab phases are verified.

## Phase 1: Single Database Consolidation

Goal: remove the split frontend/backend database setup and make backend the only database writer.

Scope:
- Move schema, migrations, seeds, and database utilities into `/database`.
- Keep the frontend read-only and API-driven.
- Preserve current behavior while consolidating storage paths.
- Verify all DB-dependent flows after the move.

Acceptance:
- One canonical database configuration.
- One shared source of truth for schema and migrations.
- Frontend does not write directly to the database.

## Phase 2: Linux Test Lab Plan

Goal: define a controlled, isolated Linux VM lab to measure detection and response behavior safely.

Scope:
- Disposable VM only, no production or shared-network exposure.
- Document test inputs, traffic replay, observation points, and cleanup.
- Measure detection timing, alert quality, and mitigation effects on future traffic.
- Keep the plan defensive and reproducible.

Acceptance:
- Lab steps are documented.
- Validation can be run safely and repeated.
- Test results can be compared before and after changes.

## Phase 3: Frontend Revamp

Goal: redesign the frontend around individual IDS engine fields and clearer operational views.

Scope:
- Add a raw event/detail view for IDs engine payloads.
- Surface source, target, ports, protocol, prediction, confidence, action, and timestamps clearly.
- Improve dashboard layout and data clarity without breaking existing routes.

Acceptance:
- Users can inspect raw IDS data and see how it maps to UI cards/tables.
- Existing dashboard functionality remains intact.

## Phase 4: Custom Decision Tree Model

Goal: add a custom decision tree model alongside the current model pipeline.

Scope:
- Keep the canonical feature schema unchanged.
- Add the model as a separate component and expose its outputs through backend contracts.
- Surface model comparisons in the UI after the revamp.

Acceptance:
- Model output is testable and visible in the UI.
- No training/runtime feature mismatch is introduced.

## Existing IDS Engine Work

The current IDS background engine work remains relevant, but it should continue only after the database consolidation and lab planning phases are stabilized.

Guardrails:
- Preserve the current packet capture flow and existing ML model artifacts.
- Keep `LiveSniffer._handle_packet` minimal: parse packets and enqueue them only.
- Do not run ML inference, database writes, network calls, file I/O, heavy aggregation, or blocking work inside the sniff callback.
- Add engine pieces in small, verified increments controlled by explicit environment variables where possible.
- Keep SmartIDS as a passive userland IDS with reactive mitigation; blocking can only affect future traffic after detection.

## Verification

- After each phase, update the relevant checklist file and run focused lint/build/tests.
- For lab work, verify in the isolated VM only.
