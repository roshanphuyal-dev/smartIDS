from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.features.realtime.engine_ws_manager import EngineWSConnectionManager


class FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self._fail = fail

    async def send_json(self, payload: dict) -> None:
        if self._fail:
            raise RuntimeError("connection broken")
        self.sent.append(payload)


class EngineWSConnectionManagerTest(unittest.TestCase):
    def test_push_command_returns_false_with_no_connections(self) -> None:
        manager = EngineWSConnectionManager()
        result = asyncio.run(manager.push_command({"command_id": "c-1"}))
        self.assertFalse(result)

    def test_push_command_delivers_envelope_to_connected_engine(self) -> None:
        manager = EngineWSConnectionManager()
        ws = FakeWebSocket()
        manager.connect(ws)

        result = asyncio.run(manager.push_command({"command_id": "c-1", "action": "block"}))

        self.assertTrue(result)
        self.assertEqual(len(ws.sent), 1)
        envelope = ws.sent[0]
        self.assertEqual(envelope["type"], "command")
        self.assertEqual(envelope["payload"], {"command_id": "c-1", "action": "block"})
        self.assertIn("id", envelope)
        self.assertIn("ts", envelope)

    def test_push_command_evicts_stale_connection_on_send_failure(self) -> None:
        manager = EngineWSConnectionManager()
        broken = FakeWebSocket(fail=True)
        manager.connect(broken)

        result = asyncio.run(manager.push_command({"command_id": "c-1"}))

        self.assertFalse(result)
        self.assertFalse(manager.has_connections())

    def test_disconnect_removes_connection(self) -> None:
        manager = EngineWSConnectionManager()
        ws = FakeWebSocket()
        manager.connect(ws)
        manager.disconnect(ws)

        self.assertFalse(manager.has_connections())
        result = asyncio.run(manager.push_command({"command_id": "c-1"}))
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
