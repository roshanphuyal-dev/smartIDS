from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.features.dashboard.service import DashboardService
from app.features.dashboard.schemas import DashboardSummaryResponse


class FakeDashboardRepository:
    def __init__(self, _session) -> None:
        pass

    async def get_summary_metrics(self) -> dict[str, int | float | bool]:
        return {
            "total_threats": 7,
            "total_sessions": 9,
            "threats_today": 5,
            "active_sessions": 3,
            "blocked_ips": 2,
            "blocked_events_today": 4,
            "watchlisted_ips": 1,
            "high_severity_threats": 4,
            "packet_queue_usage_percent": 18.5,
            "packets_received_per_30s": 42,
            "ml_predictions_per_30s": 11,
            "packet_loss_detected": False,
            "last_ml_prediction_latency_ms": 9.8,
        }

    async def get_network_threat_rollups(self, *, limit: int) -> list[dict[str, int | float | str]]:
        return [
            {
                "bucket_start": "2026-06-30T10:00:00+00:00",
                "bucket_size": "hour",
                "network_activity_total": 1200,
                "threat_event_total": 24,
                "blocked_event_total": 8,
                "threat_rate": 0.02,
            },
            {
                "bucket_start": "2026-06-30T11:00:00+00:00",
                "bucket_size": "hour",
                "network_activity_total": 1600,
                "threat_event_total": 32,
                "blocked_event_total": 10,
                "threat_rate": 0.02,
            },
        ]

    async def get_block_actions_over_time(self) -> list[dict[str, int | str]]:
        return [
            {
                "bucket": "2026-06-30 10:00",
                "count": 3,
            },
            {
                "bucket": "2026-06-30 11:00",
                "count": 5,
            },
        ]


class FakeRealtimeService:
    def __init__(self, _manager) -> None:
        self.messages = []

    async def broadcast_dashboard_metrics(self, payload) -> None:
        self.messages.append(payload)


class DashboardMetricsBroadcastTest(unittest.TestCase):
    def test_dashboard_summary_schema_includes_total_sessions(self) -> None:
        payload = DashboardSummaryResponse.model_validate(
            {
                "total_threats": 7,
                "total_sessions": 9,
                "threats_today": 5,
                "active_sessions": 3,
                "blocked_ips": 2,
                "blocked_events_today": 4,
                "watchlisted_ips": 1,
                "high_severity_threats": 4,
                "packet_queue_usage_percent": 18.5,
                "packets_received_per_30s": 42,
                "ml_predictions_per_30s": 11,
                "packet_loss_detected": False,
                "last_ml_prediction_latency_ms": 9.8,
            }
        )

        self.assertEqual(payload.total_sessions, 9)
        self.assertEqual(payload.threats_today, 5)
        self.assertEqual(payload.blocked_events_today, 4)

    def test_broadcast_summary_metrics_uses_dashboard_summary(self) -> None:
        with patch("app.features.dashboard.service.DashboardRepository", FakeDashboardRepository), patch(
            "app.features.dashboard.service.RealtimeService", FakeRealtimeService
        ):
            service = DashboardService(SimpleNamespace())

            asyncio.run(service.broadcast_summary_metrics())

        self.assertEqual(len(service._realtime_service.messages), 1)
        payload = service._realtime_service.messages[0]
        self.assertEqual(payload.metrics["total_threats"], 7)
        self.assertEqual(payload.metrics["total_sessions"], 9)
        self.assertEqual(payload.metrics["threats_today"], 5)
        self.assertEqual(payload.metrics["active_sessions"], 3)
        self.assertEqual(payload.metrics["blocked_ips"], 2)
        self.assertEqual(payload.metrics["blocked_events_today"], 4)
        self.assertEqual(payload.metrics["watchlisted_ips"], 1)
        self.assertEqual(payload.metrics["high_severity_threats"], 4)
        self.assertEqual(payload.metrics["packet_queue_usage_percent"], 18.5)
        self.assertEqual(payload.metrics["packets_received_per_30s"], 42)
        self.assertIsInstance(payload.ts, datetime)
        self.assertEqual(payload.ts.tzinfo, timezone.utc)

    def test_get_network_threat_rollups_returns_durable_series(self) -> None:
        with patch("app.features.dashboard.service.DashboardRepository", FakeDashboardRepository), patch(
            "app.features.dashboard.service.RealtimeService", FakeRealtimeService
        ):
            service = DashboardService(SimpleNamespace())
            items = asyncio.run(service.get_network_threat_rollups(limit=24))

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["bucket_size"], "hour")
        self.assertEqual(items[0]["network_activity_total"], 1200)
        self.assertEqual(items[0]["threat_event_total"], 24)
        self.assertEqual(items[1]["blocked_event_total"], 10)

    def test_get_block_actions_over_time_returns_hourly_series(self) -> None:
        with patch("app.features.dashboard.service.DashboardRepository", FakeDashboardRepository), patch(
            "app.features.dashboard.service.RealtimeService", FakeRealtimeService
        ):
            service = DashboardService(SimpleNamespace())
            items = asyncio.run(service.get_block_actions_over_time())

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["bucket"], "2026-06-30 10:00")
        self.assertEqual(items[0]["count"], 3)
        self.assertEqual(items[1]["count"], 5)
