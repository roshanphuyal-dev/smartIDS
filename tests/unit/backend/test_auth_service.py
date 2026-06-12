from __future__ import annotations

import asyncio
import os
import unittest
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

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

from app.features.auth.service import AuthService
from app.features.auth.session_tokens import hash_session_token


class FakeRedis:
    pass


class FakeUserRepository:
    def __init__(self, _session) -> None:
        self.users_by_id = {}
        self.users_by_email = {}

    async def get_by_id(self, user_id: str):
        return self.users_by_id.get(user_id)


class FakeOAuthAccountRepository:
    def __init__(self, _session) -> None:
        pass


class FakeSessionRepository:
    def __init__(self, _session) -> None:
        self.active_by_token_hash = {}
        self.revoked = []

    async def get_active_by_token_hash(self, token_hash: str):
        return self.active_by_token_hash.get(token_hash)

    async def revoke(self, session_record) -> None:
        self.revoked.append(session_record)


class AuthServiceTest(unittest.TestCase):
    def _make_service(self) -> AuthService:
        settings = SimpleNamespace(
            SESSION_SECRET="test-session-secret",
            REDIS_URL="redis://localhost:6379/0",
        )
        with patch("app.features.auth.service.redis_lib.from_url", return_value=FakeRedis()), patch(
            "app.features.auth.service.UserRepository", FakeUserRepository
        ), patch("app.features.auth.service.OAuthAccountRepository", FakeOAuthAccountRepository), patch(
            "app.features.auth.service.SessionRepository", FakeSessionRepository
        ):
            return AuthService(SimpleNamespace(), settings)

    def test_get_current_user_resolves_active_session(self) -> None:
        service = self._make_service()
        user = SimpleNamespace(id="user-1", is_active=True)
        token = "token-123"
        token_hash = hash_session_token(token)
        service._users.users_by_id[user.id] = user
        service._sessions.active_by_token_hash[token_hash] = SimpleNamespace(
            id="session-1",
            user_id=user.id,
        )

        resolved = asyncio.run(service.get_current_user(token))

        self.assertIs(resolved, user)

    def test_logout_revokes_active_session(self) -> None:
        service = self._make_service()
        token = "token-123"
        token_hash = hash_session_token(token)
        session_record = SimpleNamespace(id="session-1", user_id="user-1")
        service._sessions.active_by_token_hash[token_hash] = session_record

        asyncio.run(service.logout(token))

        self.assertEqual(service._sessions.revoked, [session_record])
