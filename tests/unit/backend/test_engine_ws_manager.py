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
    def __init__(self, fail: bool = False, fail_close: bool = False) -> None:
        self.sent: list[dict] = []
        self._fail = fail
        self._fail_close = fail_close
        self.closed_with: tuple[int, str] | None = None

    async def send_json(self, payload: dict) -> None:
        if self._fail:
            raise RuntimeError("connection broken")
        self.sent.append(payload)

    async def close(self, code: int, reason: str) -> None:
        if self._fail_close:
            raise RuntimeError("already closed")
        self.closed_with = (code, reason)


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

    def test_push_command_still_broadcasts_to_all_connections(self) -> None:
        """Regression check: adding the engine-scoped lookup must not break
        the existing flat-set broadcast used by push_command."""
        manager = EngineWSConnectionManager()
        ws_a = FakeWebSocket()
        ws_b = FakeWebSocket()
        manager.connect(ws_a, engine_public_id="engine-a")
        manager.connect(ws_b)  # global-token connection, no engine identity

        result = asyncio.run(manager.push_command({"command_id": "c-1"}))

        self.assertTrue(result)
        self.assertEqual(len(ws_a.sent), 1)
        self.assertEqual(len(ws_b.sent), 1)

    def test_push_config_update_still_broadcasts_to_all_connections(self) -> None:
        """Same regression check as above, for push_config_update."""
        manager = EngineWSConnectionManager()
        ws_a = FakeWebSocket()
        ws_b = FakeWebSocket()
        manager.connect(ws_a, engine_public_id="engine-a")
        manager.connect(ws_b)

        result = asyncio.run(manager.push_config_update({"key": "value"}))

        self.assertTrue(result)
        self.assertEqual(len(ws_a.sent), 1)
        self.assertEqual(len(ws_b.sent), 1)

    def test_force_disconnect_closes_connected_engine(self) -> None:
        manager = EngineWSConnectionManager()
        ws = FakeWebSocket()
        manager.connect(ws, engine_public_id="engine-abc")

        result = asyncio.run(manager.force_disconnect("engine-abc", code=4402, reason="revoked"))

        self.assertTrue(result)
        self.assertEqual(ws.closed_with, (4402, "revoked"))

    def test_force_disconnect_returns_false_when_engine_not_connected(self) -> None:
        manager = EngineWSConnectionManager()

        result = asyncio.run(
            manager.force_disconnect("engine-missing", code=4402, reason="revoked")
        )

        self.assertFalse(result)

    def test_force_disconnect_swallows_close_errors(self) -> None:
        manager = EngineWSConnectionManager()
        ws = FakeWebSocket(fail_close=True)
        manager.connect(ws, engine_public_id="engine-broken")

        result = asyncio.run(
            manager.force_disconnect("engine-broken", code=4402, reason="revoked")
        )

        self.assertTrue(result)

    def test_disconnect_removes_engine_scoped_entry(self) -> None:
        manager = EngineWSConnectionManager()
        ws = FakeWebSocket()
        manager.connect(ws, engine_public_id="engine-xyz")
        manager.disconnect(ws)

        result = asyncio.run(manager.force_disconnect("engine-xyz", code=4402, reason="revoked"))
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
