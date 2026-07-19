from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

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

from app.features.engines.exceptions import (
    EngineLimitExceededException,
    PendingRegistrationNotFoundException,
)
from app.features.engines.schemas import RegisterInitRequest
from app.features.engines.service import (
    MAX_ENGINES_PER_USER,
    PENDING_REGISTRATION_KEY_PREFIX,
    PENDING_REGISTRATION_TTL_SECONDS,
    EngineService,
)


class FakeEngineRepository:
    """Stand-in for EngineRepository — records what EngineService asks it to
    do without touching a real database, following the FakeUserRepository /
    FakeSessionRepository pattern used for AuthService in
    tests/unit/backend/test_auth_service.py."""

    def __init__(self) -> None:
        self.created: list = []
        self.count_by_user_return = 0

    async def count_by_user(self, user_id: str) -> int:
        return self.count_by_user_return

    async def create(self, engine):
        self.created.append(engine)
        return engine


class EngineServiceRegisterInitTest(unittest.TestCase):
    def test_register_init_stores_pending_blob_in_redis(self) -> None:
        redis_client = AsyncMock()
        service = EngineService(FakeEngineRepository(), redis_client)
        payload = RegisterInitRequest(
            registration_id="registration-id-0001",
            hostname="host-a",
            os_name="linux",
            version="1.2.3",
        )

        asyncio.run(service.register_init(payload))

        redis_client.set.assert_awaited_once()
        args, kwargs = redis_client.set.await_args
        key, stored_json = args[0], args[1]

        self.assertEqual(key, f"{PENDING_REGISTRATION_KEY_PREFIX}registration-id-0001")
        self.assertEqual(kwargs.get("ex"), PENDING_REGISTRATION_TTL_SECONDS)

        stored = json.loads(stored_json)
        self.assertEqual(stored["registration_id"], "registration-id-0001")
        self.assertEqual(stored["hostname"], "host-a")
        self.assertEqual(stored["os_name"], "linux")
        self.assertEqual(stored["version"], "1.2.3")


class EngineServiceGetPendingRegistrationTest(unittest.TestCase):
    def test_returns_expected_data_when_present(self) -> None:
        redis_client = AsyncMock()
        redis_client.get.return_value = json.dumps(
            {
                "registration_id": "reg-abc",
                "hostname": "host-b",
                "os_name": "windows",
                "version": "9.9.9",
            }
        )
        service = EngineService(FakeEngineRepository(), redis_client)

        result = asyncio.run(service.get_pending_registration("reg-abc"))

        redis_client.get.assert_awaited_once_with(f"{PENDING_REGISTRATION_KEY_PREFIX}reg-abc")
        self.assertEqual(result.registration_id, "reg-abc")
        self.assertEqual(result.hostname, "host-b")
        self.assertEqual(result.os_name, "windows")
        self.assertEqual(result.version, "9.9.9")

    def test_raises_when_missing_or_expired(self) -> None:
        redis_client = AsyncMock()
        redis_client.get.return_value = None
        service = EngineService(FakeEngineRepository(), redis_client)

        with self.assertRaises(PendingRegistrationNotFoundException):
            asyncio.run(service.get_pending_registration("reg-missing"))


class EngineServiceApproveRegistrationTest(unittest.TestCase):
    def test_creates_engine_returns_secret_and_deletes_pending_key(self) -> None:
        redis_client = AsyncMock()
        redis_client.get.return_value = json.dumps(
            {
                "registration_id": "reg-approve",
                "hostname": "host-c",
                "os_name": "linux",
                "version": "1.0.0",
            }
        )
        repository = FakeEngineRepository()
        repository.count_by_user_return = 2
        service = EngineService(repository, redis_client)

        engine, raw_secret = asyncio.run(
            service.approve_registration(
                registration_id="reg-approve", user_id="user-1", name="My Engine"
            )
        )

        self.assertEqual(len(repository.created), 1)
        created = repository.created[0]
        self.assertIs(created, engine)
        self.assertEqual(created.user_id, "user-1")
        self.assertEqual(created.name, "My Engine")
        self.assertEqual(created.hostname, "host-c")
        self.assertEqual(created.operating_system, "linux")
        self.assertEqual(created.version, "1.0.0")
        self.assertEqual(created.secret, raw_secret)
        self.assertTrue(raw_secret)

        redis_client.delete.assert_awaited_once_with(f"{PENDING_REGISTRATION_KEY_PREFIX}reg-approve")

    def test_raises_when_pending_registration_missing(self) -> None:
        redis_client = AsyncMock()
        redis_client.get.return_value = None
        service = EngineService(FakeEngineRepository(), redis_client)

        with self.assertRaises(PendingRegistrationNotFoundException):
            asyncio.run(
                service.approve_registration(registration_id="reg-x", user_id="user-1", name="Engine")
            )

    def test_enforces_max_engines_per_user_limit(self) -> None:
        redis_client = AsyncMock()
        redis_client.get.return_value = json.dumps(
            {
                "registration_id": "reg-limit",
                "hostname": None,
                "os_name": None,
                "version": None,
            }
        )
        repository = FakeEngineRepository()
        repository.count_by_user_return = MAX_ENGINES_PER_USER
        service = EngineService(repository, redis_client)

        with self.assertRaises(EngineLimitExceededException):
            asyncio.run(
                service.approve_registration(
                    registration_id="reg-limit", user_id="user-1", name="Engine"
                )
            )

        self.assertEqual(repository.created, [])
        redis_client.delete.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
