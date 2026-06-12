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

from app.features.threats.router import respond_to_threat
from app.features.threats.schemas import ThreatResponseActionRequest


class FakeThreatService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def apply_response_action(self, *, threat_id: str, action_taken: str, status: str | None):
        self.calls.append((threat_id, action_taken, status))
        return SimpleNamespace(
            id="threat-row-1",
            threat_id=threat_id,
            action_taken=action_taken,
            status=status or "open",
        )


class ThreatResponseFlowTest(unittest.TestCase):
    def test_threat_response_route_returns_unified_payload(self) -> None:
        service = FakeThreatService()
        payload = ThreatResponseActionRequest(action_taken="blocked", status="closed")

        response = asyncio.run(respond_to_threat("threat-123", payload, service=service))
        body = json.loads(response.body)

        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["threat_id"], "threat-123")
        self.assertEqual(body["data"]["action_taken"], "blocked")
        self.assertEqual(service.calls, [("threat-123", "blocked", "closed")])
