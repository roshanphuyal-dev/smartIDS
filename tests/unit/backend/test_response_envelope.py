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

from app.common.responses import create_error_response, create_response


class ResponseEnvelopeTest(unittest.TestCase):
    def test_create_response_wraps_success_envelope(self) -> None:
        response = create_response(data={"ok": True}, message="done", status_code=201)
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], "done")
        self.assertEqual(body["data"], {"ok": True})
        self.assertIn("timestamp", body["meta"])
        self.assertIn("request_id", body["meta"])

    def test_create_error_response_wraps_error_envelope(self) -> None:
        response = create_error_response(message="bad", error_code="BAD_REQUEST", details={"field": "value"}, status_code=400)
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], "bad")
        self.assertEqual(body["error_code"], "BAD_REQUEST")
        self.assertEqual(body["details"], {"field": "value"})
        self.assertIn("timestamp", body["meta"])
        self.assertIn("request_id", body["meta"])
