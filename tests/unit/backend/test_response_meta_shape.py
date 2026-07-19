from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
for path in (ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.common.responses import create_response


class ResponseMetaShapeTest(unittest.TestCase):
    def test_response_meta_has_timestamp_and_request_id(self) -> None:
        response = create_response(data={"ok": True})
        body = json.loads(response.body)

        self.assertIn("meta", body)
        self.assertIn("timestamp", body["meta"])
        self.assertIn("request_id", body["meta"])
        self.assertIsInstance(body["meta"]["timestamp"], str)
