from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.features.engine_commands.schemas import EngineCommandCreateRequest
from app.features.engine_commands.service import EngineCommandService


class FakeEngineCommandRepository:
    def __init__(self, _session) -> None:
        self.existing = None
        self.created = None

    async def get_by_command_id(self, command_id: str):
        return self.existing

    async def create(self, command):
        self.created = command
        return command


class FakeEngineWSManager:
    def __init__(self) -> None:
        self.pushed: list[dict] = []

    async def push_command(self, command: dict) -> bool:
        self.pushed.append(command)
        return True


class EngineCommandServiceWSPushTest(unittest.TestCase):
    def test_enqueue_command_pushes_over_ws_when_newly_created(self) -> None:
        fake_manager = FakeEngineWSManager()

        with (
            patch("app.features.engine_commands.service.EngineCommandRepository", side_effect=FakeEngineCommandRepository),
            patch("app.features.engine_commands.service.engine_ws_manager", fake_manager),
        ):
            service = EngineCommandService(SimpleNamespace())
            payload = EngineCommandCreateRequest(
                command_id="cmd-ws-1",
                action="block",
                ip_address="203.0.113.10",
                duration_seconds=300,
            )
            response, created = asyncio.run(service.enqueue_command(payload))

        self.assertTrue(created)
        self.assertEqual(len(fake_manager.pushed), 1)
        pushed = fake_manager.pushed[0]
        self.assertEqual(pushed["command_id"], "cmd-ws-1")
        self.assertEqual(pushed["action"], "block")
        self.assertEqual(pushed["status"], response.status)

    def test_enqueue_command_does_not_push_when_duplicate(self) -> None:
        fake_manager = FakeEngineWSManager()
        existing = SimpleNamespace(
            command_id="cmd-ws-dup",
            action="block",
            ip_address="203.0.113.11",
            duration_seconds=300,
            status="queued",
        )

        def repo_factory(_session):
            repo = FakeEngineCommandRepository(_session)
            repo.existing = existing
            return repo

        with (
            patch("app.features.engine_commands.service.EngineCommandRepository", side_effect=repo_factory),
            patch("app.features.engine_commands.service.engine_ws_manager", fake_manager),
        ):
            service = EngineCommandService(SimpleNamespace())
            payload = EngineCommandCreateRequest(
                command_id="cmd-ws-dup",
                action="block",
                ip_address="203.0.113.11",
                duration_seconds=300,
            )
            response, created = asyncio.run(service.enqueue_command(payload))

        self.assertFalse(created)
        self.assertEqual(response.status, "duplicate_ignored")
        self.assertEqual(fake_manager.pushed, [])


if __name__ == "__main__":
    unittest.main()
