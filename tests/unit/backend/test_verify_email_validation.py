from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

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

from app.features.auth.schemas import VerifyEmailRequest


class VerifyEmailValidationTest(unittest.TestCase):
    def test_verify_email_request_accepts_valid_token(self) -> None:
        payload = VerifyEmailRequest(token="verify-token")

        self.assertEqual(payload.token, "verify-token")

    def test_verify_email_request_rejects_missing_token(self) -> None:
        with self.assertRaises(ValidationError):
            VerifyEmailRequest()
