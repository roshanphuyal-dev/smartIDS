from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
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

from app.features.auth.router import logout


class FakeAuthService:
    def __init__(self) -> None:
        self.logged_out_tokens: list[str] = []

    async def logout(self, raw_token: str) -> None:
        self.logged_out_tokens.append(raw_token)


class LogoutBearerFallbackTest(unittest.TestCase):
    def test_logout_uses_bearer_token_when_cookie_missing(self) -> None:
        service = FakeAuthService()
        settings = SimpleNamespace(SESSION_COOKIE_NAME="session_token")
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "query_string": b"",
            "headers": [(b"authorization", b"Bearer bearer-token")],
        }
        request = Request(scope)

        response = asyncio.run(logout(request=request, auth_service=service, settings=settings))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(service.logged_out_tokens, ["bearer-token"])
        self.assertIn("session_token=", response.headers["set-cookie"])
