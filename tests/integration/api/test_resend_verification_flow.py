from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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

from app.features.auth.router import resend_verification_email


class FakeAuthService:
    def __init__(self) -> None:
        self.emails: list[str] = []

    async def resend_verification_email(self, email: str) -> None:
        self.emails.append(email)


class ResendVerificationFlowTest(unittest.TestCase):
    def test_resend_verification_returns_accepted_response(self) -> None:
        service = FakeAuthService()
        payload = SimpleNamespace(email="pending@example.com")

        response = asyncio.run(resend_verification_email(payload, auth_service=service))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(response.status_code, 202)
        self.assertEqual(service.emails, ["pending@example.com"])
