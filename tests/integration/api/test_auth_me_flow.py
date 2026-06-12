from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timezone
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

from app.features.auth.router import me


class AuthMeFlowTest(unittest.TestCase):
    def test_me_returns_current_user_payload(self) -> None:
        current_user = SimpleNamespace(
            id="user-1",
            email="me@example.com",
            email_verified=datetime.now(timezone.utc),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        response = json.loads(asyncio.run(me(current_user=current_user)).body)

        self.assertTrue(response["success"])
        self.assertEqual(response["data"]["user"]["email"], "me@example.com")
