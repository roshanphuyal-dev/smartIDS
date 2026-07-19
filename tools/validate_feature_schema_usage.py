"""Validate single-source FEATURE_COLUMNS usage across ML/runtime paths.

Fails if:
- FEATURE_COLUMNS is redefined outside ml/features/schema.py
- critical paths do not import FEATURE_COLUMNS
"""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "ml" / "features" / "schema.py"

CRITICAL_FILES = [
    ROOT / "feature_engine" / "extractors" / "session_feature_extractor.py",
    ROOT / "ml" / "runtime" / "live_predictor.py",
    ROOT / "ml" / "runtime" / "completed_flow_predictor.py",
]


def main() -> int:
    errors: list[str] = []

    for file_path in ROOT.rglob("*.py"):
        if ".venv" in str(file_path):
            continue
        if file_path == SCHEMA_FILE:
            continue

        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bFEATURE_COLUMNS\s*=\s*\[", text):
            errors.append(f"FEATURE_COLUMNS redefined: {file_path.relative_to(ROOT)}")

    for file_path in CRITICAL_FILES:
        if not file_path.exists():
            errors.append(f"Critical file missing: {file_path.relative_to(ROOT)}")
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        if "FEATURE_COLUMNS" not in text:
            errors.append(f"FEATURE_COLUMNS not referenced: {file_path.relative_to(ROOT)}")

    if errors:
        print("FAIL: feature schema usage validation")
        for err in errors:
            print(f"- {err}")
        return 1

    print("PASS: feature schema usage validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
