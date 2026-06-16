# Strict CICIDS2017 Dataset Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject CICIDS2017 schema drift and invalid canonical feature values consistently during training and evaluation.

**Architecture:** Add a focused validator under `ml/features` that maps raw headers, validates canonical fields and finite numeric values, and returns exactly `FEATURE_COLUMNS`. Refactor live-compatible training and evaluation preparation to call this validator.

**Tech Stack:** Python 3.12, pandas, NumPy, unittest

---

### Task 1: Shared Canonical Dataset Validator

**Files:**
- Create: `ml/features/cicids2017_validation.py`
- Create: `tests/unit/ml/test_cicids2017_validation.py`
- Modify: `ml/training/train_cicids2017_live_compatible.py`
- Modify: `ml/evaluation/evaluate_cicids2017.py`

- [x] Write failing tests for missing, extra, ordered, non-numeric, NaN, and infinite values.
- [x] Run the focused tests and confirm current zero-fill behavior fails them.
- [x] Implement the shared strict validator.
- [x] Refactor training and evaluation to use the validator.
- [x] Run focused ML tests and compile checks.
- [x] Update `backend/CHECKLIST.md` with verified results.
