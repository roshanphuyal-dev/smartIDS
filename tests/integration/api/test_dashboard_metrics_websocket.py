from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
for path in (ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

# 64 hex chars (256 bits) — satisfies Settings' production-strength validator
# even though these tests run with ENVIRONMENT=development.
TEST_SECRET = "1234567890abcdef" * 4

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")
os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.redis import get_internal_auth_redis
from app.features.realtime.router import router as realtime_router


def sign_request(method: str, path_with_query: str, body: bytes = b"") -> dict[str, str]:
    """Build valid x-smartids-* signing headers, mirroring the production
    signing-string construction in app.common.internal_auth."""
    timestamp = str(time.time())
    nonce = "test-nonce-0000000000000000"
    body_hash = hashlib.sha256(body).hexdigest()
    signing_string = f"{method.upper()}\n{path_with_query}\n{body_hash}\n{timestamp}\n{nonce}"
    signature = hmac.new(TEST_SECRET.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
    return {
        "x-smartids-signature": signature,
        "x-smartids-timestamp": timestamp,
        "x-smartids-nonce": nonce,
        "Content-Type": "application/json",
    }


class FakeAsyncRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis's SET NX EX usage."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and name in self._store:
            return None
        self._store[name] = value
        return True


app = FastAPI()
app.include_router(realtime_router, prefix="/api/v1")
app.dependency_overrides[get_internal_auth_redis] = lambda: FakeAsyncRedis()


class DashboardMetricsWebSocketTest(unittest.TestCase):
    def setUp(self) -> None:
        # get_settings() is a process-wide lru_cache singleton; another test
        # module may have already cached a Settings instance with a different
        # SMARTIDS_INTERNAL_SERVICE_TOKEN before this test runs.
        os.environ["SMARTIDS_INTERNAL_SERVICE_TOKEN"] = TEST_SECRET
        get_settings.cache_clear()

    def test_dashboard_metrics_broadcast_reaches_websocket_client(self) -> None:
        payload = {
            "ts": datetime(2026, 6, 8, tzinfo=timezone.utc).isoformat(),
            "metrics": {
                "total_threats": 12,
                "total_sessions": 9,
                "threats_today": 6,
                "active_sessions": 4,
                "blocked_ips": 3,
                "blocked_events_today": 2,
                "watchlisted_ips": 1,
                "high_severity_threats": 2,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        headers = sign_request("POST", "/api/v1/realtime/broadcast/dashboard", body=body)

        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/ws") as websocket:
                response = client.post(
                    "/api/v1/realtime/broadcast/dashboard", content=body, headers=headers
                )
                self.assertEqual(response.status_code, 200)

                message = websocket.receive_json()
                self.assertEqual(message["channel"], "dashboard_metrics")
                self.assertEqual(message["payload"]["metrics"]["total_threats"], 12)
                self.assertEqual(message["payload"]["metrics"]["total_sessions"], 9)
                self.assertEqual(message["payload"]["metrics"]["threats_today"], 6)
                self.assertEqual(message["payload"]["metrics"]["active_sessions"], 4)
                self.assertEqual(message["payload"]["metrics"]["blocked_ips"], 3)
                self.assertEqual(message["payload"]["metrics"]["blocked_events_today"], 2)
                self.assertEqual(message["payload"]["metrics"]["watchlisted_ips"], 1)
                self.assertEqual(message["payload"]["metrics"]["high_severity_threats"], 2)
