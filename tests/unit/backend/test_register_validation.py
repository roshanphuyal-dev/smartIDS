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

from app.features.auth.schemas import RegisterRequest


class RegisterValidationTest(unittest.TestCase):
    def test_register_request_accepts_valid_payload(self) -> None:
        payload = RegisterRequest(full_name="Jane Doe", email="jane@example.com", password="secret123")

        self.assertEqual(payload.full_name, "Jane Doe")
        self.assertEqual(payload.email, "jane@example.com")
        self.assertEqual(payload.password, "secret123")

    def test_register_request_rejects_missing_full_name(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(email="jane@example.com", password="secret123")

    def test_register_request_rejects_short_password(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(full_name="Jane Doe", email="jane@example.com", password="short")
