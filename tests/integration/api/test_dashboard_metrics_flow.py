from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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

from app.features.blocked_ips.schemas import ManualBlockRequest, ManualWatchlistRequest
from app.features.blocked_ips.service import BlockedIPService
from app.features.engine_commands.schemas import EngineCommandResponse
from app.features.sessions.schemas import NetworkSessionUpsertRequest
from app.features.sessions.service import NetworkSessionService


class FakeNetworkSession:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
        self.updated_at = kwargs.get("updated_at", datetime.now(timezone.utc))
        self.created_at = kwargs.get("created_at", self.updated_at)


class FakeSessionRepository:
    def __init__(self, _session) -> None:
        self.existing = None
        self.created = None
        self.saved = None

    async def get_by_session_id(self, _session_id: str):
        return self.existing

    async def create(self, session_row):
        self.created = session_row
        return session_row

    async def save(self, session_row):
        self.saved = session_row
        return session_row

    async def list_sessions(self, **_kwargs):
        return [], 0


class FakeDashboardService:
    def __init__(self, _session) -> None:
        self.broadcasts = 0

    async def broadcast_summary_metrics(self) -> None:
        self.broadcasts += 1


class FakeRealtimeService:
    def __init__(self, _manager) -> None:
        self.messages = []

    async def broadcast_session_update(self, payload) -> None:
        self.messages.append(payload)

    async def broadcast_traffic_update(self, payload) -> None:
        self.messages.append(payload)

    async def broadcast_blocked_ip_update(self, payload) -> None:
        self.messages.append(payload)


class FakeEngineCommandService:
    def __init__(self, _session) -> None:
        self.commands = []

    async def enqueue_command(self, payload):
        self.commands.append(payload)
        return (
            EngineCommandResponse(
                command_id=payload.command_id,
                action=payload.action,
                ip_address=str(payload.ip_address),
                duration_seconds=payload.duration_seconds,
                status="queued",
            ),
            True,
        )


class FakeBlockedIPRepository:
    def __init__(self, _session) -> None:
        pass

    async def list_ip_summaries(self, status: str | None = None):
        return []

    async def get_ip_activity(self, ip_address: str):
        return []


class DashboardMetricsFlowTest(unittest.TestCase):
    def test_session_upsert_triggers_dashboard_metrics_broadcast(self) -> None:
        session_service_state = {}

        def session_repo_factory(_session):
            repo = FakeSessionRepository(_session)
            session_service_state["repo"] = repo
            return repo

        def dashboard_factory(_session):
            dashboard = FakeDashboardService(_session)
            session_service_state["dashboard"] = dashboard
            return dashboard

        with patch("app.features.sessions.service.NetworkSessionRepository", side_effect=session_repo_factory), patch(
            "app.features.sessions.service.DashboardService", side_effect=dashboard_factory
        ), patch("app.features.sessions.service.RealtimeService", FakeRealtimeService), patch(
            "app.features.sessions.service.NetworkSession", FakeNetworkSession
        ):
            service = NetworkSessionService(SimpleNamespace())
            payload = NetworkSessionUpsertRequest(
                session_id="session-123",
                start_time=datetime(2026, 6, 8, tzinfo=timezone.utc),
                end_time=None,
                source_ip="10.0.0.1",
                destination_ip="10.0.0.2",
                source_port=1234,
                destination_port=80,
                protocol=6,
                packet_count=5,
                byte_count=2048,
                duration=3.5,
                risk_score=0.9,
                ml_prediction="SQL Injection",
                heuristic_result="suspicious",
                state="active",
            )

            asyncio.run(service.upsert_session(payload))

        self.assertEqual(session_service_state["dashboard"].broadcasts, 1)

    def test_manual_block_triggers_dashboard_metrics_broadcast(self) -> None:
        dashboard = FakeDashboardService(SimpleNamespace())

        with patch("app.features.blocked_ips.service.RealtimeService", FakeRealtimeService):
            service = BlockedIPService(
                FakeBlockedIPRepository(SimpleNamespace()),
                FakeEngineCommandService(SimpleNamespace()),
                dashboard,
            )
            payload = ManualBlockRequest(ip_address="10.0.0.9", reason="manual block", duration_seconds=60)

            asyncio.run(service.manual_block(payload))

        self.assertEqual(dashboard.broadcasts, 1)

    def test_manual_unblock_triggers_dashboard_metrics_broadcast(self) -> None:
        dashboard = FakeDashboardService(SimpleNamespace())

        with patch("app.features.blocked_ips.service.RealtimeService", FakeRealtimeService):
            service = BlockedIPService(
                FakeBlockedIPRepository(SimpleNamespace()),
                FakeEngineCommandService(SimpleNamespace()),
                dashboard,
            )

            asyncio.run(service.manual_unblock("10.0.0.9"))

        self.assertEqual(dashboard.broadcasts, 1)

    def test_manual_watchlist_triggers_dashboard_metrics_broadcast(self) -> None:
        dashboard = FakeDashboardService(SimpleNamespace())

        with patch("app.features.blocked_ips.service.RealtimeService", FakeRealtimeService):
            service = BlockedIPService(
                FakeBlockedIPRepository(SimpleNamespace()),
                FakeEngineCommandService(SimpleNamespace()),
                dashboard,
            )
            payload = ManualWatchlistRequest(ip_address="10.0.0.9", reason="manual watchlist")

            asyncio.run(service.manual_watchlist(payload))

        self.assertEqual(dashboard.broadcasts, 1)
