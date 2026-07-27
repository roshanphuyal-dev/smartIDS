"""Async seed runner for SmartIDS backend database."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from .bootstrap import bootstrap_environment

bootstrap_environment()

from app.db.session import async_session_factory, engine
from app.features.alerts.models import Alert
from app.features.analytics_rollups.models import NetworkThreatRollup
from app.features.api_keys.models import APIKey
from app.features.auth.models import OAuthAccount, Session, User
from app.features.block_events.models import BlockEvent
from app.features.engine_commands.models import EngineCommand
from app.features.engine_telemetry.models import EngineTelemetrySnapshot
from app.features.engines.models import Engine
from app.features.geolocation.models import IpLocation
from app.features.ids_events.models import IDSEvent
from app.features.ip_control_state.models import IPControlState
from app.features.sessions.models import NetworkSession
from app.features.sql_injection.models import SQLInjectionEvent
from app.features.auth.schemas import LoginRequest
from app.features.auth.service import AuthService
from app.features.dashboard.repository import DashboardRepository
from app.features.sessions.repository import NetworkSessionRepository
from app.features.sessions.schemas import NetworkSessionFilters
from app.features.threats.repository import ThreatRepository
from app.features.threats.schemas import ThreatFilters

from .dataset import DemoCredential, SeedPlan, build_seed_plan


@dataclass
class EntityCounts:
    created: int = 0
    reused: int = 0
    deleted: int = 0
    skipped: int = 0


@dataclass
class SeedReport:
    entities: dict[str, EntityCounts] = field(default_factory=OrderedDict)
    demo_credentials: list[DemoCredential] = field(default_factory=list)
    excluded_tables: list[tuple[str, str]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)

    def entity(self, name: str) -> EntityCounts:
        return self.entities.setdefault(name, EntityCounts())


class SeedRunner:
    """Coordinates reset, seed, and validation flows."""

    def __init__(self) -> None:
        self.plan: SeedPlan = build_seed_plan()
        self.report = SeedReport(
            demo_credentials=self.plan.demo_credentials,
            excluded_tables=[(item.table_name, item.reason) for item in self.plan.excluded_tables],
            assumptions=[
                "Backend auth model has no role/RBAC column; demo accounts differ by ownership and account state only.",
                "Notifications excluded because current migration chain does not create `notifications`, and model FK targets nonexistent `threats` table.",
                "Seed rows use explicit `seed_*` primary keys so reruns never assume numeric PK sequences.",
            ],
        )

    async def run(self, *, reset: bool, validate: bool) -> SeedReport:
        existing_tables = await self._get_table_names()
        if "users" not in existing_tables:
            raise RuntimeError(
                "Required backend tables missing. Run `cd backend && python script.py migrate upgrade` first."
            )

        if reset:
            print("Reset seed-owned rows.")
            await self._reset_seed_rows()

        print("Seed users/auth tables.")
        await self._seed_users_auth()
        print("Seed runtime/app tables.")
        await self._seed_runtime_tables()

        if validate:
            print("Validate seeded data.")
            await self._validate_seed_data()

        return self.report

    async def _seed_users_auth(self) -> None:
        async with async_session_factory() as session:
            async with session.begin():
                await self._bulk_upsert(session, User, self.plan.users, "users")
                await self._bulk_upsert(session, OAuthAccount, self.plan.oauth_accounts, "oauth_accounts")
                await self._bulk_upsert(session, Session, self.plan.auth_sessions, "auth_sessions")
                await self._bulk_upsert(session, IpLocation, self.plan.ip_locations, "ip_locations")
                await self._bulk_upsert(session, APIKey, self.plan.api_keys, "api_keys")
                await self._bulk_upsert(session, Engine, self.plan.engines, "engines")

    async def _seed_runtime_tables(self) -> None:
        async with async_session_factory() as session:
            async with session.begin():
                await self._bulk_upsert(session, NetworkSession, self.plan.network_sessions, "network_sessions")
                await self._bulk_upsert(session, IDSEvent, self.plan.ids_events, "ids_events")
                await self._bulk_upsert(session, Alert, self.plan.alerts, "alerts")
                await self._bulk_upsert(session, SQLInjectionEvent, self.plan.sql_injection_events, "sql_injection_events")
                await self._bulk_upsert(session, EngineCommand, self.plan.engine_commands, "engine_commands")
                await self._bulk_upsert(session, BlockEvent, self.plan.block_events, "block_events")
                await self._bulk_upsert(session, IPControlState, self.plan.ip_control_states, "ip_control_states")
                await self._bulk_upsert(session, EngineTelemetrySnapshot, self.plan.engine_telemetry_snapshots, "engine_telemetry_snapshots")
                await self._bulk_upsert(session, NetworkThreatRollup, self.plan.network_threat_rollups, "network_threat_rollups")

    async def _reset_seed_rows(self) -> None:
        async with async_session_factory() as session:
            async with session.begin():
                for model, label in (
                    (NetworkThreatRollup, "network_threat_rollups"),
                    (EngineTelemetrySnapshot, "engine_telemetry_snapshots"),
                    (IPControlState, "ip_control_states"),
                    (BlockEvent, "block_events"),
                    (EngineCommand, "engine_commands"),
                    (SQLInjectionEvent, "sql_injection_events"),
                    (Alert, "alerts"),
                    (IDSEvent, "ids_events"),
                    (NetworkSession, "network_sessions"),
                    (User, "users"),
                ):
                    result = await session.execute(
                        delete(model).where(model.id.like("seed_%"))
                    )
                    self.report.entity(label).deleted += int(result.rowcount or 0)

    async def _bulk_upsert(
        self,
        session,
        model,
        rows: list[dict[str, Any]],
        label: str,
    ) -> None:
        if not rows:
            return

        table = model.__table__
        row_ids = [row["id"] for row in rows]
        existing_ids = set(
            (
                await session.execute(
                    select(table.c.id).where(table.c.id.in_(row_ids))
                )
            ).scalars()
        )

        insert_stmt = pg_insert(table).values(rows)
        update_columns = {
            column.name: insert_stmt.excluded[column.name]
            for column in table.columns
            if column.name not in {"id", "created_at"}
        }
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[table.c.id],
            set_=update_columns,
        )

        try:
            await session.execute(stmt)
        except IntegrityError as exc:
            raise RuntimeError(
                f"Seed conflict while writing `{label}`. Existing non-seed rows likely collide with seed-owned unique fields. "
                f"Resolve conflicting records first. Original error: {exc.orig}"
            ) from exc

        entity_counts = self.report.entity(label)
        entity_counts.created += len(rows) - len(existing_ids)
        entity_counts.reused += len(existing_ids)

    async def _validate_seed_data(self) -> None:
        async with async_session_factory() as session:
            dashboard_repo = DashboardRepository(session)
            threat_repo = ThreatRepository(session)
            session_repo = NetworkSessionRepository(session)

            summary = await dashboard_repo.get_summary_metrics()
            if summary["total_threats"] < 1 or summary["total_sessions"] < 1:
                raise RuntimeError("Dashboard summary validation failed: expected non-empty alerts and sessions.")
            self.report.validation_notes.append(
                f"Dashboard summary OK: total_threats={summary['total_threats']} total_sessions={summary['total_sessions']} blocked_ips={summary['blocked_ips']}"
            )

            threats, threat_total = await threat_repo.list_threats(
                filters=ThreatFilters(),
                limit=5,
                offset=0,
            )
            if threat_total < 1 or not threats:
                raise RuntimeError("Threat service validation failed: expected threat rows.")
            self.report.validation_notes.append(
                f"Threat listing OK: first threat={threats[0].threat_id or threats[0].id} total={threat_total}"
            )

            sessions, session_total = await session_repo.list_sessions(
                filters=NetworkSessionFilters(),
                limit=5,
                offset=0,
            )
            if session_total < 1 or not sessions:
                raise RuntimeError("Session service validation failed: expected session rows.")
            self.report.validation_notes.append(
                f"Session listing OK: first session={sessions[0].session_id} total={session_total}"
            )

            ids_event_missing_sessions = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(IDSEvent)
                        .where(
                            IDSEvent.id.like("seed_%"),
                            IDSEvent.session_id.is_not(None),
                            IDSEvent.session_id.not_in(
                                select(NetworkSession.session_id).where(NetworkSession.id.like("seed_%"))
                            ),
                        )
                    )
                ).scalar_one()
            )
            alert_missing_sessions = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Alert)
                        .where(
                            Alert.id.like("seed_%"),
                            Alert.session_id.is_not(None),
                            Alert.session_id.not_in(
                                select(NetworkSession.session_id).where(NetworkSession.id.like("seed_%"))
                            ),
                        )
                    )
                ).scalar_one()
            )
            block_missing_sessions = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(BlockEvent)
                        .where(
                            BlockEvent.id.like("seed_%"),
                            BlockEvent.session_id.is_not(None),
                            BlockEvent.session_id.not_in(
                                select(NetworkSession.session_id).where(NetworkSession.id.like("seed_%"))
                            ),
                        )
                    )
                ).scalar_one()
            )
            if ids_event_missing_sessions or alert_missing_sessions or block_missing_sessions:
                raise RuntimeError(
                    "String-linked relationship validation failed for seeded session references."
                )
            self.report.validation_notes.append(
                "Session-link validation OK: seeded IDS events, alerts, and block events all reference seeded network sessions."
            )

        await self._validate_auth_login()

    async def _validate_auth_login(self) -> None:
        async with async_session_factory() as session:
            auth_service = AuthService(session)
            login_request = LoginRequest(
                email="analyst@smartids-demo.dev",
                password="AnalystPass!123",
            )
            user, raw_token = await auth_service.login(
                login_request,
                user_agent="seed-validator",
                ip_address="127.0.0.1",
            )
            if user.email != "analyst@smartids-demo.dev" or not raw_token:
                raise RuntimeError("Demo auth validation failed.")
            self.report.validation_notes.append(
                f"Demo auth OK: analyst login created transient session for user_id={user.id}"
            )
            await session.rollback()

    async def _get_table_names(self) -> set[str]:
        async with engine.begin() as connection:
            return set(
                await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).get_table_names()
                )
            )
