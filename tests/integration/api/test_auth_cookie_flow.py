from __future__ import annotations

import asyncio
import importlib.metadata
import os
import unittest
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

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
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

if "authlib" not in sys.modules:
    authlib_module = types.ModuleType("authlib")
    integrations_module = types.ModuleType("authlib.integrations")
    httpx_client_module = types.ModuleType("authlib.integrations.httpx_client")

    class _DummyAsyncOAuth2Client:  # pragma: no cover - test harness stub
        def __init__(self, *args, **kwargs):
            pass

        def create_authorization_url(self, *args, **kwargs):
            return ("", None)

        async def fetch_token(self, *args, **kwargs):
            return {}

        async def get(self, *args, **kwargs):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {},
            )

    httpx_client_module.AsyncOAuth2Client = _DummyAsyncOAuth2Client
    integrations_module.httpx_client = httpx_client_module
    authlib_module.integrations = integrations_module
    sys.modules["authlib"] = authlib_module
    sys.modules["authlib.integrations"] = integrations_module
    sys.modules["authlib.integrations.httpx_client"] = httpx_client_module

if "argon2" not in sys.modules:
    argon2_module = types.ModuleType("argon2")
    argon2_exceptions_module = types.ModuleType("argon2.exceptions")

    class _DummyPasswordHasher:  # pragma: no cover - test harness stub
        def hash(self, value):
            return f"hashed:{value}"

        def verify(self, hashed, value):
            return hashed == f"hashed:{value}"

    argon2_module.PasswordHasher = _DummyPasswordHasher
    argon2_exceptions_module.InvalidHashError = ValueError
    argon2_exceptions_module.VerifyMismatchError = ValueError
    sys.modules["argon2"] = argon2_module
    sys.modules["argon2.exceptions"] = argon2_exceptions_module

if "email_validator" not in sys.modules:
    email_validator_module = types.ModuleType("email_validator")

    class _DummyEmailNotValidError(ValueError):
        pass

    def _dummy_validate_email(email, *args, **kwargs):  # pragma: no cover - test harness stub
        return types.SimpleNamespace(email=email, normalized=email, local_part=email.split("@", 1)[0])

    email_validator_module.EmailNotValidError = _DummyEmailNotValidError
    email_validator_module.validate_email = _dummy_validate_email
    sys.modules["email_validator"] = email_validator_module

_original_metadata_version = importlib.metadata.version


def _metadata_version(name: str) -> str:
    if name == "email-validator":
        return "2.0.0"
    return _original_metadata_version(name)


importlib.metadata.version = _metadata_version

if "authlib" not in sys.modules:
    pass

from app.features.auth.dependencies import _extract_session_token, clear_session_cookie, get_current_user, set_session_cookie
from app.common.exception_handlers import register_exception_handlers
from app.core.config import get_settings
from app.features.auth.dependencies import get_auth_service
from app.features.auth.router import router as auth_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


class FakeAuthService:
    def __init__(self) -> None:
        self.tokens = []
        now = datetime.now(timezone.utc)
        self.user = SimpleNamespace(
            id="user-1",
            email="user@example.com",
            email_verified=now,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

    async def get_current_user(self, raw_token: str):
        self.tokens.append(raw_token)
        return self.user

    async def login(self, payload, user_agent=None, ip_address=None):
        self.tokens.append((payload.email, user_agent, ip_address))
        return self.user, "raw-session-token"

    async def logout(self, raw_token: str):
        self.tokens.append(("logout", raw_token))

    def build_oauth_authorization_url(self, provider_name: str):
        return f"https://example.com/oauth/{provider_name}"

    async def handle_oauth_callback(self, provider_name: str, code: str, state: str, user_agent=None, ip_address=None):
        self.tokens.append(("oauth", provider_name, code, state, user_agent, ip_address))
        return self.user, "oauth-session-token"


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

    def test_login_logout_and_oauth_cookie_flow(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=get_settings().frontend_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        app.include_router(auth_router, prefix="/api")

        fake_service = FakeAuthService()
        app.dependency_overrides[get_auth_service] = lambda: fake_service

        with TestClient(app) as client:
            login_resp = client.post(
                "/api/auth/login",
                headers={"Origin": "http://localhost:3000"},
                json={"email": "user@example.com", "password": "password123"},
            )
            self.assertEqual(login_resp.status_code, 200)
            self.assertIn("session_token=raw-session-token", login_resp.headers["set-cookie"])
            self.assertEqual(login_resp.headers["access-control-allow-origin"], "http://localhost:3000")

            me_resp = client.get("/api/auth/me")
            self.assertEqual(me_resp.status_code, 200)
            self.assertEqual(me_resp.json()["data"]["user"]["email"], "user@example.com")

            oauth_callback_resp = client.get(
                "/api/auth/oauth/github/callback?code=abc&state=xyz",
            )
            self.assertEqual(oauth_callback_resp.status_code, 200)
            self.assertIn("session_token=oauth-session-token", oauth_callback_resp.headers["set-cookie"])

            logout_resp = client.post("/api/auth/logout")
            self.assertEqual(logout_resp.status_code, 200)
            self.assertIn("session_token=", logout_resp.headers["set-cookie"])
