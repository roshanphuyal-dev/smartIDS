# Staged CICIDS2017 Model Build Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, verify, and atomically activate a complete live-compatible CICIDS2017 model bundle with one command.

**Architecture:** Add a build orchestrator under `ml/training` that validates prepared dataset metadata, trains and evaluates inside a same-filesystem staging directory, verifies artifacts through the runtime loader, writes manifest and sample contracts, then swaps the staged directory into place with rollback.

**Tech Stack:** Python 3.12, pandas, NumPy, scikit-learn, XGBoost, joblib, unittest

---

### Task 1: Model Bundle Contracts And Activation

**Files:**
- Create: `ml/training/build_cicids2017_model.py`
- Create: `ml/contracts/live_prediction_input.example.json`
- Create: `ml/contracts/live_prediction_output.example.json`
- Create: `tests/unit/ml/test_build_cicids2017_model.py`

- [x] Write failing tests for dataset metadata validation, manifest/sample contracts, successful activation, and activation rollback.
- [x] Run tests and verify the build module is missing.
- [x] Implement staged build helpers and rollback-safe activation.
- [x] Implement training, evaluation, runtime loading, and sample prediction verification.
- [x] Add static input/output contract examples.
- [x] Run focused ML tests and compile checks.
- [x] Update docs and `backend/CHECKLIST.md` with the final command and next action.
