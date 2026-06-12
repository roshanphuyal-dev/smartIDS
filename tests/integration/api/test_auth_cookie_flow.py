from __future__ import annotations

import asyncio
import os
import unittest
import sys
from types import SimpleNamespace
from pathlib import Path

from fastapi import Response
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

from app.features.auth.dependencies import _extract_session_token, clear_session_cookie, get_current_user, set_session_cookie


class FakeAuthService:
    def __init__(self) -> None:
        self.tokens = []

    async def get_current_user(self, raw_token: str):
        self.tokens.append(raw_token)
        return SimpleNamespace(id="user-1", email="user@example.com")


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": headers,
    }
    return Request(scope)


class AuthCookieFlowTest(unittest.TestCase):
    def test_cookie_helpers_set_and_clear_session_cookie(self) -> None:
        response = Response()
        settings = SimpleNamespace(
            SESSION_COOKIE_NAME="session_token",
            SESSION_COOKIE_SECURE=False,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_TTL_SECONDS=3600,
        )

        set_session_cookie(response, "raw-token", settings)
        self.assertIn("session_token=raw-token", response.headers["set-cookie"])

        cleared_response = Response()
        clear_session_cookie(cleared_response, settings)
        cleared_cookie_header = cleared_response.headers["set-cookie"]
        self.assertIn("session_token=", cleared_cookie_header)
        self.assertTrue("expires=" in cleared_cookie_header.lower() or "max-age=0" in cleared_cookie_header.lower())

    def test_extract_session_token_prefers_cookie_over_bearer(self) -> None:
        settings = SimpleNamespace(SESSION_COOKIE_NAME="session_token")
        request = _request_with_headers([
            (b"cookie", b"session_token=cookie-token"),
            (b"authorization", b"Bearer bearer-token"),
        ])

        self.assertEqual(_extract_session_token(request, settings), "cookie-token")

    def test_get_current_user_uses_cookie_token(self) -> None:
        settings = SimpleNamespace(SESSION_COOKIE_NAME="session_token")
        request = _request_with_headers([(b"cookie", b"session_token=cookie-token")])
        auth_service = FakeAuthService()

        user = asyncio.run(get_current_user(request, auth_service=auth_service, settings=settings))

        self.assertEqual(user.email, "user@example.com")
        self.assertEqual(auth_service.tokens, ["cookie-token"])
