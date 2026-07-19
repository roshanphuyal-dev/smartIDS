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

from app.features.auth.router import login, logout


class FakeAuthService:
    def __init__(self) -> None:
        self.logged_out_tokens: list[str] = []

    async def login(self, payload, *, user_agent=None, ip_address=None):
        user = SimpleNamespace(
            id="user-1",
            email="user@example.com",
            email_verified=datetime.now(timezone.utc),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return user, "raw-login-token"

    async def logout(self, raw_token: str) -> None:
        self.logged_out_tokens.append(raw_token)


def _request(headers: list[tuple[bytes, bytes]], cookies: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "query_string": b"",
        "headers": headers,
    }
    request = Request(scope)
    if cookies:
        request._cookies = cookies  # type: ignore[attr-defined]
    return request


class LoginLogoutFlowTest(unittest.TestCase):
    def test_login_sets_cookie_and_returns_user(self) -> None:
        service = FakeAuthService()
        settings = SimpleNamespace(
            SESSION_COOKIE_NAME="session_token",
            SESSION_COOKIE_SECURE=False,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_TTL_SECONDS=3600,
        )
        request = _request([(b"user-agent", b"pytest")])
        payload = SimpleNamespace(email="user@example.com", password="password123")

        response = asyncio.run(login(payload, request=request, auth_service=service, settings=settings))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["user"]["email"], "user@example.com")
        self.assertIn("session_token=raw-login-token", response.headers["set-cookie"])

    def test_logout_uses_cookie_token_when_present(self) -> None:
        service = FakeAuthService()
        settings = SimpleNamespace(SESSION_COOKIE_NAME="session_token")
        request = _request(
            [(b"cookie", b"session_token=cookie-token")],
            cookies={"session_token": "cookie-token"},
        )

        response = asyncio.run(logout(request=request, auth_service=service, settings=settings))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(service.logged_out_tokens, ["cookie-token"])
        self.assertIn("session_token=", response.headers["set-cookie"])
