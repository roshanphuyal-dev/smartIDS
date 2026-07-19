from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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

from app.features.sessions.router import respond_to_network_session
from app.features.sessions.schemas import NetworkSessionResponseActionRequest


class FakeSessionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def apply_response_action(self, *, session_id: str, action_taken: str, state: str | None):
        self.calls.append((session_id, action_taken, state))
        return SimpleNamespace(
            session_id=session_id,
            state=state or action_taken,
        )


class SessionResponseFlowTest(unittest.TestCase):
    def test_session_response_route_returns_unified_payload(self) -> None:
        service = FakeSessionService()
        payload = NetworkSessionResponseActionRequest(action_taken="watchlisted", state="watchlisted")

        response = asyncio.run(respond_to_network_session("session-123", payload, service=service))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["session_id"], "session-123")
        self.assertEqual(body["data"]["state"], "watchlisted")
        self.assertEqual(service.calls, [("session-123", "watchlisted", "watchlisted")])
