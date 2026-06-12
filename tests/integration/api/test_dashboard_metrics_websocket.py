from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

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

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.features.realtime.router import router as realtime_router


app = FastAPI()
app.include_router(realtime_router, prefix="/api/v1")


class DashboardMetricsWebSocketTest(unittest.TestCase):
    def test_dashboard_metrics_broadcast_reaches_websocket_client(self) -> None:
        payload = {
            "ts": datetime(2026, 6, 8, tzinfo=timezone.utc).isoformat(),
            "metrics": {
                "total_threats": 12,
                "active_sessions": 4,
                "blocked_ips": 3,
                "watchlisted_ips": 1,
                "high_severity_threats": 2,
            },
        }

        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/realtime/ws") as websocket:
                response = client.post("/api/v1/realtime/broadcast/dashboard", json=payload)
                self.assertEqual(response.status_code, 200)

                message = websocket.receive_json()
                self.assertEqual(message["channel"], "dashboard_metrics")
                self.assertEqual(message["payload"]["metrics"]["total_threats"], 12)
                self.assertEqual(message["payload"]["metrics"]["active_sessions"], 4)
                self.assertEqual(message["payload"]["metrics"]["blocked_ips"], 3)
                self.assertEqual(message["payload"]["metrics"]["watchlisted_ips"], 1)
                self.assertEqual(message["payload"]["metrics"]["high_severity_threats"], 2)
