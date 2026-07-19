from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.features.block_events.schemas import BlockEventUpsertRequest
from app.features.block_events.service import BlockEventService


class FakeBlockEvent:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
        self.id = kwargs.get("id", "evt-db-1")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
        self.updated_at = kwargs.get("updated_at", self.created_at)


class FakeBlockEventRepository:
    def __init__(self, _session) -> None:
        self.existing = None
        self.created = None
        self.saved = None

    async def get_by_event_id(self, _event_id: str):
        return self.existing

    async def create(self, event):
        self.created = event
        return event

    async def save(self, event):
        self.saved = event
        return event


class FakeBlockedIPRepository:
    def __init__(self, _session) -> None:
        self.summary = {
            "ip_address": "57.144.40.1",
            "status": "blocked",
            "reason": "manual_block",
            "first_detected": datetime(2026, 6, 30, tzinfo=timezone.utc),
            "last_detected": datetime(2026, 6, 30, 0, 1, tzinfo=timezone.utc),
            "total_attempts": 3,
            "attack_types": ["manual_block"],
            "last_action": "blocked",
            "source": "manual",
        }

    async def get_ip_summary(self, _ip_address: str):
        return self.summary


class FakeRealtimeService:
    def __init__(self, _manager) -> None:
        self.messages = []

    async def broadcast_blocked_ip_update(self, payload) -> None:
        self.messages.append(payload)


class FakeDashboardService:
    def __init__(self, _session) -> None:
        self.broadcasts = 0

    async def broadcast_summary_metrics(self) -> None:
        self.broadcasts += 1


class FakeIPControlStateService:
    def __init__(self, _session) -> None:
        self.payloads = []

    async def apply_block_event(self, payload) -> None:
        self.payloads.append(payload)


class FakeAnalyticsRollupService:
    def __init__(self, _session) -> None:
        self.payloads = []

    async def record_block_event(self, payload) -> None:
        self.payloads.append(payload)


class BlockEventRealtimePersistenceTest(unittest.TestCase):
    def test_upsert_broadcasts_db_backed_blocked_ip_summary_and_dashboard_metrics(self) -> None:
        state = {}

        def block_event_repo_factory(_session):
            repo = FakeBlockEventRepository(_session)
            state["block_repo"] = repo
            return repo

        def blocked_ip_repo_factory(_session):
            repo = FakeBlockedIPRepository(_session)
            state["blocked_repo"] = repo
            return repo

        def dashboard_factory(_session):
            dashboard = FakeDashboardService(_session)
            state["dashboard"] = dashboard
            return dashboard

        def ip_control_state_factory(_session):
            service = FakeIPControlStateService(_session)
            state["ip_control"] = service
            return service

        def analytics_factory(_session):
            service = FakeAnalyticsRollupService(_session)
            state["analytics"] = service
            return service

        with (
            patch("app.features.block_events.service.BlockEventRepository", side_effect=block_event_repo_factory),
            patch("app.features.block_events.service.BlockedIPRepository", side_effect=blocked_ip_repo_factory),
            patch("app.features.block_events.service.DashboardService", side_effect=dashboard_factory),
            patch("app.features.block_events.service.AnalyticsRollupService", side_effect=analytics_factory),
            patch("app.features.block_events.service.IPControlStateService", side_effect=ip_control_state_factory),
            patch("app.features.block_events.service.RealtimeService", FakeRealtimeService),
            patch("app.features.block_events.service.BlockEvent", FakeBlockEvent),
        ):
            service = BlockEventService(SimpleNamespace())
            payload = BlockEventUpsertRequest(
                event_id="evt-1",
                timestamp=datetime(2026, 6, 30, tzinfo=timezone.utc),
                source_ip="57.144.40.1",
                action_taken="blocked",
                reason="manual_block",
                detection_method="manual",
                session_id=None,
                source_port=None,
                destination_ip=None,
                destination_port=None,
                protocol=None,
            )

            event, created = asyncio.run(service.upsert(payload))

        self.assertTrue(created)
        self.assertEqual(event.source_ip, "57.144.40.1")
        self.assertEqual(state["dashboard"].broadcasts, 1)
        self.assertEqual(len(state["analytics"].payloads), 1)
        self.assertEqual(len(state["ip_control"].payloads), 1)
        self.assertEqual(state["ip_control"].payloads[0].action_taken, "blocked")
        self.assertEqual(len(service._realtime_service.messages), 1)
        message = service._realtime_service.messages[0]
        self.assertEqual(message.ip_address, "57.144.40.1")
        self.assertEqual(message.status, "blocked")
        self.assertEqual(message.total_attempts, 3)
        self.assertEqual(message.last_action, "blocked")
        self.assertEqual(message.source, "manual")
