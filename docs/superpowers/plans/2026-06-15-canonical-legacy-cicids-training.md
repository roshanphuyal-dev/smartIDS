# Canonical Legacy CICIDS2017 Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the legacy CICIDS2017 training command supported while enforcing the canonical live-compatible feature schema.

**Architecture:** Specialize `CICIDS2017Loader` at the dataset boundary: map CICIDS2017 headers, validate all canonical fields, and select exactly `FEATURE_COLUMNS`. The training command continues using the loader and therefore inherits the canonical contract without duplicating feature logic.

**Tech Stack:** Python 3.12, pandas, NumPy, scikit-learn, unittest

---

### Task 1: Canonical CICIDS2017 Feature Selection

**Files:**
- Modify: `ml/datasets/cicids2017_loader.py`
- Create: `tests/unit/ml/test_cicids2017_loader_features.py`

- [x] **Step 1: Write failing tests**

Add tests that build a dataframe containing every canonical feature, using raw CICIDS2017 names where mappings exist, and assert that `split_features_labels()` returns exactly `FEATURE_COLUMNS`. Add cases proving extra numeric columns are ignored and missing canonical fields raise a descriptive `ValueError`.

- [x] **Step 2: Run tests and verify failure**

Run:

```powershell
.\.venv_windows\Scripts\python.exe -m unittest tests.unit.ml.test_cicids2017_loader_features
```

Expected: failures showing inferred extra columns remain and missing canonical columns are not rejected as required.

- [x] **Step 3: Implement canonical mapping and validation**

Import `CICIDS2017_TO_INTERNAL` and `FEATURE_COLUMNS` in `CICIDS2017Loader`. Map headers before generic cleaning, validate missing fields in `split_features_labels()`, select `df[FEATURE_COLUMNS]`, sanitize numeric values, and set `self.feature_columns` to a copy of `FEATURE_COLUMNS`.

- [x] **Step 4: Run focused tests**

Run:

```powershell
.\.venv_windows\Scripts\python.exe -m unittest tests.unit.ml.test_cicids2017_loader_features tests.unit.ml.test_feature_schema tests.unit.ml.test_feature_columns_guards tests.unit.ml.test_feature_columns_order
```

Expected: all tests pass.

- [x] **Step 5: Record completion**

Mark the relevant items complete in `backend/CHECKLIST.md` and add a dated impact note describing the canonical loader contract.
