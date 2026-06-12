from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.features.dashboard.service import DashboardService


class FakeDashboardRepository:
    def __init__(self, _session) -> None:
        pass

    async def get_summary_metrics(self) -> dict[str, int]:
        return {
            "total_threats": 7,
            "active_sessions": 3,
            "blocked_ips": 2,
            "watchlisted_ips": 1,
            "high_severity_threats": 4,
        }


class FakeRealtimeService:
    def __init__(self, _manager) -> None:
        self.messages = []

    async def broadcast_dashboard_metrics(self, payload) -> None:
        self.messages.append(payload)


class DashboardMetricsBroadcastTest(unittest.TestCase):
    def test_broadcast_summary_metrics_uses_dashboard_summary(self) -> None:
        with patch("app.features.dashboard.service.DashboardRepository", FakeDashboardRepository), patch(
            "app.features.dashboard.service.RealtimeService", FakeRealtimeService
        ):
            service = DashboardService(SimpleNamespace())

            asyncio.run(service.broadcast_summary_metrics())

        self.assertEqual(len(service._realtime_service.messages), 1)
        payload = service._realtime_service.messages[0]
        self.assertEqual(payload.metrics["total_threats"], 7)
        self.assertEqual(payload.metrics["active_sessions"], 3)
        self.assertEqual(payload.metrics["blocked_ips"], 2)
        self.assertEqual(payload.metrics["watchlisted_ips"], 1)
        self.assertEqual(payload.metrics["high_severity_threats"], 4)
        self.assertIsInstance(payload.ts, datetime)
        self.assertEqual(payload.ts.tzinfo, timezone.utc)
