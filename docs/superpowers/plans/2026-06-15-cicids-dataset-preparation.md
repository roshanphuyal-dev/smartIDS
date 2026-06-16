# CICIDS2017 Dataset Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate validated, reproducible CICIDS2017 train/test datasets and provenance metadata from verified raw exports.

**Architecture:** Add a focused CLI module under `ml/datasets` that loads sorted source CSVs, calls the shared strict feature validator, normalizes labels, performs a seeded stratified split, and writes outputs plus hashes and distributions. Keep existing training and evaluation commands pointed at the generated filenames.

**Tech Stack:** Python 3.12, pandas, scikit-learn, hashlib, argparse, unittest

---

### Task 1: Reproducible Dataset Preparation CLI

**Files:**
- Create: `ml/datasets/prepare_cicids2017.py`
- Create: `tests/unit/ml/test_prepare_cicids2017.py`
- Modify: `backend/CHECKLIST.md`

- [x] Write failing tests for canonical outputs, deterministic split metadata, source/output hashes, overwrite protection, and no writes on validation failure.
- [x] Run tests and confirm the preparation API is missing.
- [x] Implement the preparation API and CLI.
- [x] Run focused and broader ML tests.
- [x] Run the command against the current bundled CSV and confirm it fails without writing outputs because four canonical fields are absent.
- [x] Update the shared checklist with results and the next action.
