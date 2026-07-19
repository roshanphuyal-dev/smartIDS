from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from starlette.requests import Request

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

from app.features.auth.router import verify_email


class FakeAuthService:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def verify_email(self, token: str):
        self.tokens.append(token)
        user = SimpleNamespace(
            id="user-1",
            email="verified@example.com",
            email_verified=datetime.now(timezone.utc),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return user, "verified-session-token"


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": headers,
    }
    return Request(scope)


class VerifyEmailFlowTest(unittest.TestCase):
    def test_verify_email_sets_session_cookie_and_returns_user(self) -> None:
        service = FakeAuthService()
        settings = SimpleNamespace(
            SESSION_COOKIE_NAME="session_token",
            SESSION_COOKIE_SECURE=False,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_TTL_SECONDS=3600,
        )
        request = _request([(b"user-agent", b"pytest")])
        payload = SimpleNamespace(token="verify-token")

        response = asyncio.run(verify_email(payload, request=request, auth_service=service, settings=settings))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["user"]["email"], "verified@example.com")
        self.assertIn("session_token=verified-session-token", response.headers["set-cookie"])
        self.assertEqual(service.tokens, ["verify-token"])
