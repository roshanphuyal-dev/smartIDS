"""Bootstrap helpers for repo-root seed scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare system Python
    load_dotenv = None

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"


def bootstrap_environment() -> None:
    """Make backend app imports and env settings available from repo root."""
    for path in (ROOT, BACKEND_ROOT):
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

    env_path = BACKEND_ROOT / ".env"
    if load_dotenv is not None:
        load_dotenv(env_path, override=False)
        return

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
