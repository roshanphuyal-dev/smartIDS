from __future__ import annotations

import os
import unittest
import sys
from types import SimpleNamespace
from pathlib import Path

from fastapi import Response

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

from app.features.auth.dependencies import clear_session_cookie, set_session_cookie


class AuthCookieHelpersTest(unittest.TestCase):
    def test_set_session_cookie_uses_http_only_cookie(self) -> None:
        response = Response()
        settings = SimpleNamespace(
            SESSION_COOKIE_NAME="session_token",
            SESSION_COOKIE_SECURE=False,
            SESSION_COOKIE_SAMESITE="lax",
            SESSION_TTL_SECONDS=3600,
        )

        set_session_cookie(response, "raw-token", settings)

        cookie_header = response.headers["set-cookie"]
        self.assertIn("session_token=raw-token", cookie_header)
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("Path=/", cookie_header)

    def test_clear_session_cookie_removes_cookie(self) -> None:
        response = Response()
        settings = SimpleNamespace(SESSION_COOKIE_NAME="session_token")

        clear_session_cookie(response, settings)

        cookie_header = response.headers["set-cookie"]
        self.assertIn("session_token=", cookie_header)
        self.assertTrue("expires=" in cookie_header.lower() or "max-age=0" in cookie_header.lower())
