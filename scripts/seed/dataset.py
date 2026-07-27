"""Deterministic seed dataset for local SmartIDS development/demo use."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .bootstrap import bootstrap_environment

bootstrap_environment()

from app.features.api_keys.key_utils import hash_api_secret
from app.features.auth.password import hash_password
from app.features.auth.session_tokens import hash_session_token

SEED_PREFIX = "seed_"
SEED_NOW = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
SEED_DOMAIN = "smartids-demo.dev"
SEED_OWNER_NOTE = "[seed] smartids demo dataset"


@dataclass(frozen=True)
class DemoCredential:
    label: str
    email: str
    password: str | None
    notes: str


@dataclass(frozen=True)
class ExcludedTable:
    table_name: str
    reason: str


@dataclass(frozen=True)
class SeedPlan:
    users: list[dict]
    oauth_accounts: list[dict]
    auth_sessions: list[dict]
    ip_locations: list[dict]
    api_keys: list[dict]
    engines: list[dict]
    network_sessions: list[dict]
    ids_events: list[dict]
    alerts: list[dict]
    sql_injection_events: list[dict]
    engine_commands: list[dict]
    block_events: list[dict]
    ip_control_states: list[dict]
    engine_telemetry_snapshots: list[dict]
    network_threat_rollups: list[dict]
    demo_credentials: list[DemoCredential]
    excluded_tables: list[ExcludedTable]


def _stamp(record: dict, *, created_at: datetime, updated_at: datetime | None = None) -> dict:
    stamped = dict(record)
    stamped.setdefault("created_at", created_at)
    stamped.setdefault("updated_at", updated_at or created_at)
    return stamped


def _stable_secret(label: str, *, length: int = 48) -> str:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()
    while len(digest) < length:
        digest += hashlib.sha256(digest.encode("utf-8")).hexdigest()
    return digest[:length]


def _build_users() -> tuple[list[dict], list[dict], list[DemoCredential]]:
    verified_at = SEED_NOW - timedelta(days=45)
    users_spec = [
        ("seed_user_admin", f"admin@{SEED_DOMAIN}", "Avery Admin", "AdminPass!123", True, verified_at, "Primary demo account. Current app has no role column; use as owner/admin-named account only."),
        ("seed_user_manager", f"manager@{SEED_DOMAIN}", "Morgan Manager", "ManagerPass!123", True, verified_at + timedelta(days=1), "Manager-named account. No role/RBAC column exists in schema."),
        ("seed_user_analyst", f"analyst@{SEED_DOMAIN}", "Alex Analyst", "AnalystPass!123", True, verified_at + timedelta(days=2), "Recommended login for dashboard/testing."),
        ("seed_user_operator", f"operator@{SEED_DOMAIN}", "Olivia Operator", "OperatorPass!123", True, verified_at + timedelta(days=3), "Owns most engine registrations."),
        ("seed_user_demo", f"demo@{SEED_DOMAIN}", "Dana Demo", "DemoPass!123", True, verified_at + timedelta(days=4), "General non-empty-state account."),
        ("seed_user_qa", f"qa@{SEED_DOMAIN}", "Quinn QA", "QaPass!12345", True, verified_at + timedelta(days=5), "Extra account for pagination/search coverage."),
        ("seed_user_inactive", f"inactive@{SEED_DOMAIN}", "Iris Inactive", "InactivePass!123", False, verified_at + timedelta(days=6), "Inactive account. Login should fail."),
        ("seed_user_pending", f"pending@{SEED_DOMAIN}", "Parker Pending", "PendingPass!123", True, None, "Unverified account. Login should fail until verified."),
        ("seed_user_oauth_alice", f"github.alice@{SEED_DOMAIN}", "Alice OAuth", None, True, verified_at + timedelta(days=7), "OAuth-only GitHub account. No password hash."),
        ("seed_user_oauth_bob", f"github.bob@{SEED_DOMAIN}", "Bob OAuth", None, True, verified_at + timedelta(days=8), "OAuth-only GitHub account. No password hash."),
    ]

    users: list[dict] = []
    oauth_accounts: list[dict] = []
    demo_credentials: list[DemoCredential] = []

    for index, (user_id, email, full_name, password, is_active, email_verified, notes) in enumerate(users_spec):
        created_at = SEED_NOW - timedelta(days=90 - index * 4)
        users.append(
            _stamp(
                {
                    "id": user_id,
                    "email": email,
                    "full_name": full_name,
                    "password_hash": hash_password(password) if password else None,
                    "email_verified": email_verified,
                    "is_active": is_active,
                },
                created_at=created_at,
                updated_at=max(created_at, email_verified or created_at),
            )
        )
        demo_credentials.append(
            DemoCredential(
                label=full_name,
                email=email,
                password=password,
                notes=notes,
            )
        )

    oauth_accounts.extend(
        [
            _stamp(
                {
                    "id": "seed_oauth_account_alice",
                    "user_id": "seed_user_oauth_alice",
                    "provider": "github",
                    "provider_user_id": "seed-github-alice",
                    "provider_email": f"github.alice@{SEED_DOMAIN}",
                },
                created_at=SEED_NOW - timedelta(days=32),
            ),
            _stamp(
                {
                    "id": "seed_oauth_account_bob",
                    "user_id": "seed_user_oauth_bob",
                    "provider": "github",
                    "provider_user_id": "seed-github-bob",
                    "provider_email": f"github.bob@{SEED_DOMAIN}",
                },
                created_at=SEED_NOW - timedelta(days=31),
            ),
        ]
    )
    return users, oauth_accounts, demo_credentials


def _build_auth_sessions() -> tuple[list[dict], list[dict]]:
    session_specs = [
        ("seed_auth_session_admin_current", "seed_user_admin", "admin-current", 14, 14, None, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0", "203.0.113.10", "Seattle", "US"),
        ("seed_auth_session_admin_old", "seed_user_admin", "admin-old", 41, 34, None, "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/617.1.3", "203.0.113.11", "Portland", "US"),
        ("seed_auth_session_manager_current", "seed_user_manager", "manager-current", 9, 9, None, "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0", "203.0.113.12", "Denver", "US"),
        ("seed_auth_session_analyst_current", "seed_user_analyst", "analyst-current", 2, 2, None, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/126.0.0.0", "203.0.113.13", "Austin", "US"),
        ("seed_auth_session_analyst_mobile", "seed_user_analyst", "analyst-mobile", 19, 18, None, "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Safari/604.1", "203.0.113.14", "Austin", "US"),
        ("seed_auth_session_operator_current", "seed_user_operator", "operator-current", 1, 1, None, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0", "203.0.113.15", "Dallas", "US"),
        ("seed_auth_session_demo_current", "seed_user_demo", "demo-current", 4, 4, None, "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Chrome/125.0.0.0", "203.0.113.16", "Chicago", "US"),
        ("seed_auth_session_demo_revoked", "seed_user_demo", "demo-revoked", 28, 26, SEED_NOW - timedelta(days=22), "Mozilla/5.0 (Linux; Android 15) Chrome/126.0.0.0", "203.0.113.17", "Chicago", "US"),
        ("seed_auth_session_qa_current", "seed_user_qa", "qa-current", 6, 6, None, "Mozilla/5.0 (X11; Linux x86_64) Firefox/127.0", "203.0.113.18", "Boston", "US"),
        ("seed_auth_session_qa_tablet", "seed_user_qa", "qa-tablet", 12, 11, None, "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) Safari/604.1", "203.0.113.19", "Boston", "US"),
        ("seed_auth_session_inactive", "seed_user_inactive", "inactive-current", 5, 5, None, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0", "203.0.113.20", "Phoenix", "US"),
        ("seed_auth_session_pending", "seed_user_pending", "pending-current", 3, 3, None, "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) Safari/617.1.3", "203.0.113.21", "Miami", "US"),
    ]
    sessions: list[dict] = []
    ip_locations: list[dict] = []

    for index, (session_id, user_id, token_label, age_days, created_days, revoked_at, user_agent, ip_address, city, country_code) in enumerate(session_specs):
        created_at = SEED_NOW - timedelta(days=created_days, hours=index)
        expires_at = SEED_NOW + timedelta(days=30 - min(age_days, 20))
        if "old" in token_label:
            expires_at = SEED_NOW + timedelta(days=7)
        if "inactive" in token_label or "pending" in token_label:
            expires_at = SEED_NOW + timedelta(days=15)
        raw_token = f"seed-session-token::{token_label}"
        sessions.append(
            _stamp(
                {
                    "id": session_id,
                    "user_id": user_id,
                    "token_hash": hash_session_token(raw_token),
                    "expires_at": expires_at,
                    "revoked_at": revoked_at,
                    "user_agent": user_agent,
                    "ip_address": ip_address,
                },
                created_at=created_at,
                updated_at=revoked_at or (created_at + timedelta(hours=12)),
            )
        )

        if revoked_at is not None:
            continue

        ip_locations.append(
            _stamp(
                {
                    "id": f"seed_ip_location_{index:02d}",
                    "user_id": user_id,
                    "session_id": session_id,
                    "ip_address": ip_address,
                    "country": "United States",
                    "country_code": country_code,
                    "state": "Seed State",
                    "state_code": "SS",
                    "city": city,
                    "postal_code": f"{73000 + index}",
                    "latitude": 30.0 + index * 0.5,
                    "longitude": -97.0 + index * 0.25,
                    "timezone": "America/Chicago",
                    "provider": "seed-offline",
                    "resolved_at": created_at + timedelta(minutes=5),
                },
                created_at=created_at + timedelta(minutes=5),
            )
        )
    return sessions, ip_locations


def _build_api_keys() -> list[dict]:
    specs = [
        ("seed_api_key_admin_live", "seed_user_admin", "Admin Live Key", "Backend automation", "live", "v1", True, None),
        ("seed_api_key_admin_test", "seed_user_admin", "Admin Test Key", "Staging validation", "test", "v1", True, None),
        ("seed_api_key_manager_live", "seed_user_manager", "Manager Reports", "Exports + reporting", "live", "v1", True, None),
        ("seed_api_key_analyst_dev", "seed_user_analyst", "Analyst Dev", "Notebook experiments", "development", "v1", True, None),
        ("seed_api_key_analyst_old", "seed_user_analyst", "Analyst Retired", "Disabled historical key", "test", "v1", False, SEED_NOW - timedelta(days=5)),
        ("seed_api_key_operator_live", "seed_user_operator", "Engine Registration", "Engine bootstrap", "live", "v1", True, None),
        ("seed_api_key_operator_v2", "seed_user_operator", "Operator V2 Trial", "Future key shape trial", "development", "v2", True, None),
        ("seed_api_key_demo_live", "seed_user_demo", "Demo Integrations", "Shared sandbox integrations", "live", "v1", True, None),
        ("seed_api_key_demo_test", "seed_user_demo", "Demo Expiring", "Expires soon for UI state", "test", "v1", True, SEED_NOW + timedelta(days=3)),
        ("seed_api_key_qa_test", "seed_user_qa", "QA Regression", "Regression suite", "test", "v1", True, None),
    ]
    api_keys: list[dict] = []
    for index, (row_id, user_id, name, description, environment, version, is_active, expires_at) in enumerate(specs):
        key_id = f"seedkey{index:02d}"
        secret = _stable_secret(f"{row_id}-secret", length=64)
        api_keys.append(
            _stamp(
                {
                    "id": row_id,
                    "user_id": user_id,
                    "name": name,
                    "description": description,
                    "key_id": key_id,
                    "environment": environment,
                    "version": version,
                    "key_hash": hash_api_secret(secret),
                    "is_active": is_active,
                    "expires_at": expires_at,
                },
                created_at=SEED_NOW - timedelta(days=50 - index * 2),
            )
        )
    return api_keys


def _build_engines() -> list[dict]:
    specs = [
        ("seed_engine_01", "seed_user_operator", "Warehouse Sensor", "seed-engine-warehouse", "warehouse-host", "Linux", "1.4.2", "198.51.100.10", "active", SEED_NOW - timedelta(minutes=4), None),
        ("seed_engine_02", "seed_user_operator", "Branch Sensor", "seed-engine-branch", "branch-host", "Windows", "1.4.1", "198.51.100.11", "active", SEED_NOW - timedelta(minutes=14), None),
        ("seed_engine_03", "seed_user_analyst", "Lab Sensor", "seed-engine-lab", "lab-host", "Linux", "1.3.9", "198.51.100.12", "active", SEED_NOW - timedelta(hours=2), None),
        ("seed_engine_04", "seed_user_demo", "Retired Demo Sensor", "seed-engine-retired", "retired-host", "Linux", "1.2.0", "198.51.100.13", "revoked", SEED_NOW - timedelta(days=3), SEED_NOW - timedelta(days=7)),
    ]
    engines: list[dict] = []
    for index, (row_id, user_id, name, public_id, hostname, operating_system, version, ip_address, status, last_seen, revoked_at) in enumerate(specs):
        created_at = SEED_NOW - timedelta(days=70 - index * 8)
        engines.append(
            _stamp(
                {
                    "id": row_id,
                    "user_id": user_id,
                    "name": name,
                    "engine_public_id": public_id,
                    "secret": _stable_secret(f"{row_id}-engine-secret", length=96),
                    "previous_secret": _stable_secret(f"{row_id}-previous-secret", length=96) if row_id == "seed_engine_03" else None,
                    "previous_secret_expires_at": SEED_NOW + timedelta(days=1) if row_id == "seed_engine_03" else None,
                    "hostname": hostname,
                    "operating_system": operating_system,
                    "version": version,
                    "ip_address": ip_address,
                    "status": status,
                    "last_seen": last_seen,
                    "revoked_at": revoked_at,
                    "heartbeat_interval_seconds": 30,
                },
                created_at=created_at,
                updated_at=max(created_at, revoked_at or last_seen or created_at),
            )
        )
    return engines


def _build_network_sessions() -> list[dict]:
    attack_types = ["DDoS", "PortScan", "Brute Force", "SQL Injection", "Bot", "DoS"]
    destinations = [
        ("10.10.0.10", 443),
        ("10.10.0.11", 80),
        ("10.10.0.12", 22),
        ("10.10.0.13", 5432),
        ("10.10.0.14", 3306),
    ]
    malicious_ips = [f"198.51.100.{50 + index}" for index in range(12)]
    benign_ips = [f"203.0.113.{40 + index}" for index in range(20)]

    sessions: list[dict] = []
    for index in range(60):
        is_attack = index % 5 in {0, 1}
        start_time = SEED_NOW - timedelta(hours=72 - index, minutes=(index * 7) % 60)
        end_time = None if index < 8 else start_time + timedelta(seconds=45 + index * 11)
        last_seen_at = end_time or (SEED_NOW - timedelta(minutes=5 + index))
        protocol = 1 if index % 11 == 0 else (17 if index % 2 else 6)
        source_port = None if protocol == 1 else 20000 + index * 17
        destination_ip, destination_port = destinations[index % len(destinations)]
        prediction = attack_types[index % len(attack_types)] if is_attack else "Normal Traffic"
        risk_score = round(0.72 + (index % 6) * 0.04, 2) if is_attack else round(0.03 + (index % 4) * 0.04, 2)
        packet_count = 5 + index * 3
        duration_seconds = float(20 + index * 6)
        state = "active" if index < 8 else ("blocked" if is_attack and index % 3 == 0 else "closed")
        sessions.append(
            _stamp(
                {
                    "id": f"seed_network_session_{index:03d}",
                    "session_id": f"seed-session-{index:03d}",
                    "start_time": start_time,
                    "end_time": end_time,
                    "last_seen_at": last_seen_at,
                    "source_ip": malicious_ips[index % len(malicious_ips)] if is_attack else benign_ips[index % len(benign_ips)],
                    "destination_ip": destination_ip,
                    "source_port": source_port,
                    "destination_port": destination_port,
                    "protocol": protocol,
                    "packet_count": packet_count,
                    "byte_count": packet_count * (420 if is_attack else 180),
                    "duration": duration_seconds,
                    "risk_score": risk_score,
                    "ml_prediction": prediction,
                    "heuristic_result": "suspicious" if is_attack and index % 2 == 0 else ("benign" if not is_attack else None),
                    "state": state,
                },
                created_at=start_time,
                updated_at=last_seen_at,
            )
        )
    return sessions


def _build_ids_events(network_sessions: list[dict]) -> list[dict]:
    ids_events: list[dict] = []
    for session_index, session_row in enumerate(network_sessions):
        benign = (session_row["ml_prediction"] or "").lower() == "normal traffic"
        event_count = 4
        for stage in range(event_count):
            ts = session_row["start_time"] + timedelta(seconds=stage * 20 + 5)
            prediction = session_row["ml_prediction"]
            severity = "low"
            action = "allow"
            action_taken = "allowed"
            if not benign:
                severity = "medium" if stage < 2 else ("high" if stage == 2 else "critical")
                action = "alert" if stage < 2 else "block"
                action_taken = "watchlist" if stage == 1 else ("block" if stage >= 2 else "alert")
            confidence = round(min(0.99, session_row["risk_score"] + stage * 0.05), 2)
            ids_events.append(
                _stamp(
                    {
                        "id": f"seed_ids_event_row_{session_index:03d}_{stage}",
                        "event_id": f"seed-event-{session_index:03d}-{stage}",
                        "schema_version": "1.0",
                        "ts": ts,
                        "source": session_row["source_ip"],
                        "model": "xgboost_primary",
                        "prediction": prediction,
                        "confidence": confidence,
                        "severity": severity,
                        "action": action,
                        "protocol": session_row["protocol"],
                        "source_ip": session_row["source_ip"],
                        "destination_ip": session_row["destination_ip"],
                        "source_port": session_row["source_port"],
                        "destination_port": session_row["destination_port"],
                        "attack_type": prediction,
                        "session_id": session_row["session_id"],
                        "features": {
                            "seed_owner": True,
                            "session_packet_count": session_row["packet_count"],
                            "session_byte_count": session_row["byte_count"],
                            "session_duration": session_row["duration"],
                            "response_history": ["observe"] if benign else ["observe", action_taken],
                            "risk_score": session_row["risk_score"],
                            "is_final": stage == event_count - 1,
                            "model_outputs": {
                                "primary": {
                                    "prediction": prediction,
                                    "confidence": confidence,
                                },
                                "secondary": {
                                    "prediction": prediction if not benign else "Normal Traffic",
                                    "confidence": round(max(confidence - 0.07, 0.01), 2),
                                },
                            },
                        },
                    },
                    created_at=ts,
                )
            )
    return ids_events


def _build_alerts(network_sessions: list[dict], ids_events: list[dict]) -> list[dict]:
    ids_by_event_id = {row["event_id"]: row for row in ids_events}
    alerts: list[dict] = []
    alert_index = 0
    for session_index, session_row in enumerate(network_sessions):
        prediction = session_row["ml_prediction"] or "Normal Traffic"
        if prediction == "Normal Traffic":
            continue
        for variant, action_taken, status in (
            ("watch", "watchlist", "open"),
            ("block", "blocked", "resolved" if session_index % 4 == 0 else "investigating"),
        ):
            event_stage = 1 if variant == "watch" else 3
            event = ids_by_event_id[f"seed-event-{session_index:03d}-{event_stage}"]
            detected_at = event["ts"]
            last_seen_at = detected_at + timedelta(minutes=(session_index % 5) * 7 + (3 if variant == "block" else 0))
            alerts.append(
                _stamp(
                    {
                        "id": f"seed_alert_row_{alert_index:03d}",
                        "dedup_key": f"seed-alert-{session_row['session_id']}-{variant}",
                        "event_id": event["event_id"],
                        "prediction": prediction,
                        "severity": "high" if variant == "watch" else "critical",
                        "confidence": event["confidence"],
                        "action": "alert" if variant == "watch" else "block",
                        "source": "ids_engine",
                        "status": status,
                        "first_seen_at": detected_at,
                        "last_seen_at": last_seen_at,
                        "occurrence_count": 2 + (session_index % 5),
                        "threat_id": f"seed-threat-{session_index:03d}-{variant}",
                        "detection_method": "ml",
                        "action_taken": action_taken,
                        "session_id": session_row["session_id"],
                        "source_ip": session_row["source_ip"],
                        "destination_ip": session_row["destination_ip"],
                        "source_port": session_row["source_port"],
                        "destination_port": session_row["destination_port"],
                        "protocol": session_row["protocol"],
                        "risk_score": session_row["risk_score"],
                        "is_final": variant == "block",
                        "title": f"{prediction} {variant} alert",
                        "description": f"{prediction} activity detected against {session_row['destination_ip']}:{session_row['destination_port']}.",
                        "target_ip": session_row["destination_ip"],
                        "port": session_row["destination_port"],
                        "country": "US",
                        "attack_type": prediction,
                        "metadata_json": {
                            "seed_owner": True,
                            "engine": "seed-engine-warehouse" if session_index % 2 == 0 else "seed-engine-branch",
                            "event_ids": [f"seed-event-{session_index:03d}-{event_stage}"],
                        },
                        "detected_at": detected_at,
                        "resolved_at": last_seen_at if status == "resolved" else None,
                    },
                    created_at=detected_at,
                    updated_at=last_seen_at,
                )
            )
            alert_index += 1
    return alerts


def _build_block_events_and_state(network_sessions: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    targeted_sessions: list[dict] = []
    seen_ips: set[str] = set()
    for row in network_sessions:
        if row["ml_prediction"] == "Normal Traffic":
            continue
        source_ip = row["source_ip"]
        if source_ip in seen_ips:
            continue
        seen_ips.add(source_ip)
        targeted_sessions.append(row)
        if len(targeted_sessions) == 12:
            break
    block_events: list[dict] = []
    engine_commands: list[dict] = []
    ip_control_states: list[dict] = []

    for index, session_row in enumerate(targeted_sessions):
        source_ip = session_row["source_ip"]
        sequence = [
            ("watchlist", "manual" if index % 3 == 0 else "ml", "Queued for observation"),
            ("block", "ml", "Escalated after repeated detections"),
            ("unblock" if index % 4 == 0 else "watchlist", "manual" if index % 4 == 0 else "ml", "Analyst follow-up"),
            ("block" if index % 2 == 0 else "watchlist", "ml", "Latest confirmed posture"),
        ]
        latest_event: dict | None = None
        latest_command: dict | None = None
        for event_offset, (action_taken, detection_method, reason) in enumerate(sequence):
            ts = session_row["start_time"] + timedelta(minutes=event_offset * 17 + 8)
            block_event = _stamp(
                {
                    "id": f"seed_block_event_row_{index:02d}_{event_offset}",
                    "event_id": f"seed-block-{index:02d}-{event_offset}",
                    "ts": ts,
                    "source_ip": source_ip,
                    "action_taken": action_taken,
                    "reason": reason,
                    "detection_method": detection_method,
                    "session_id": session_row["session_id"],
                    "source_port": session_row["source_port"],
                    "destination_ip": session_row["destination_ip"],
                    "destination_port": session_row["destination_port"],
                    "protocol": session_row["protocol"],
                },
                created_at=ts,
            )
            block_events.append(block_event)
            latest_event = block_event

            command_status = "acknowledged" if event_offset < 3 else ("queued" if index % 3 == 0 else "delivered")
            ack_status = None
            acked_at = None
            delivered_at = None
            ack_source = None
            if command_status in {"delivered", "acknowledged"}:
                delivered_at = ts + timedelta(seconds=20)
            if command_status == "acknowledged":
                ack_status = "blocked" if action_taken == "block" else action_taken
                acked_at = ts + timedelta(seconds=45)
                ack_source = "seed_runtime"
            command = _stamp(
                {
                    "id": f"seed_engine_command_row_{index:02d}_{event_offset}",
                    "command_id": f"seed-cmd-{index:02d}-{event_offset}",
                    "action": "unwatchlist" if action_taken == "unblock" else action_taken,
                    "ip_address": source_ip,
                    "duration_seconds": 900 if action_taken == "block" else 300,
                    "status": command_status,
                    "ack_status": ack_status,
                    "ack_source": ack_source,
                    "delivered_at": delivered_at,
                    "acked_at": acked_at,
                },
                created_at=ts - timedelta(seconds=30),
                updated_at=acked_at or delivered_at or ts,
            )
            engine_commands.append(command)
            latest_command = command

        latest_action = (latest_event or {})["action_taken"]
        current_status = "blocked" if latest_action == "block" else ("watchlisted" if latest_action == "watchlist" else "unblocked")
        ip_control_states.append(
            _stamp(
                {
                    "id": f"seed_ip_control_state_{index:02d}",
                    "ip_address": source_ip,
                    "current_status": current_status,
                    "control_source": "seed",
                    "reason": (latest_event or {})["reason"],
                    "first_blocked_at": block_events[-4]["ts"] if sequence[1][0] == "block" else None,
                    "last_changed_at": (latest_event or {})["ts"],
                    "expires_at": (latest_event or {})["ts"] + timedelta(minutes=45) if current_status == "blocked" else None,
                    "last_command_id": (latest_command or {})["command_id"],
                    "last_block_event_id": (latest_event or {})["event_id"],
                    "last_session_id": session_row["session_id"],
                },
                created_at=session_row["start_time"],
                updated_at=(latest_event or {})["ts"],
            )
        )
    return block_events, engine_commands, ip_control_states


def _build_sql_injection_events() -> list[dict]:
    sql_events: list[dict] = []
    paths = ["/api/search", "/api/login", "/api/report", "/api/export"]
    for index in range(24):
        detected = index % 3 == 0
        ts = SEED_NOW - timedelta(hours=36 - index)
        sql_events.append(
            _stamp(
                {
                    "id": f"seed_sql_event_row_{index:03d}",
                    "request_id": f"seed-sql-{index:03d}",
                    "ts": ts,
                    "source": f"proxy:{paths[index % len(paths)]}",
                    "query_preview": "' OR '1'='1 --" if detected else f"SELECT * FROM audit_log WHERE id = {1000 + index}",
                    "detected": detected,
                    "confidence": 0.94 if detected else 0.04,
                    "reason": "classic tautology payload" if detected else None,
                    "decision": "block" if detected else "allow",
                    "http_status": 400 if detected else 200,
                },
                created_at=ts,
            )
        )
    return sql_events


def _build_engine_telemetry(network_sessions: list[dict]) -> tuple[list[dict], list[dict]]:
    telemetry_rows: list[dict] = []
    rollups: list[dict] = []
    for index in range(36):
        ts = SEED_NOW - timedelta(hours=72 - index * 2)
        active_sessions = 6 + (index % 7)
        packets_received_per_30s = 1200 + index * 18
        ml_predictions_per_30s = 26 + (index % 8) * 3
        queue_usage = round(14.5 + (index % 9) * 6.2, 2)
        active_exchanges = []
        for session_row in network_sessions[index % len(network_sessions): (index % len(network_sessions)) + 3]:
            active_exchanges.append(
                {
                    "source_ip": session_row["source_ip"],
                    "destination_ip": session_row["destination_ip"],
                    "source_port": session_row["source_port"],
                    "destination_port": session_row["destination_port"],
                    "protocol": session_row["protocol"],
                    "packet_count": session_row["packet_count"],
                    "byte_count": session_row["byte_count"],
                    "duration": session_row["duration"],
                }
            )
        telemetry_rows.append(
            _stamp(
                {
                    "id": f"seed_engine_telemetry_{index:03d}",
                    "ts": ts,
                    "packets_received_total": 50000 + index * 2200,
                    "packets_received_per_30s": packets_received_per_30s,
                    "packets_processed_total": 49800 + index * 2180,
                    "packets_dropped_total": 20 + index,
                    "packets_lost_total": 10 + (index % 4),
                    "packet_loss_detected": index % 10 == 0,
                    "packet_queue_size": 18 + (index % 11),
                    "packet_queue_maxsize": 128,
                    "packet_queue_usage_percent": queue_usage,
                    "active_sessions": active_sessions,
                    "ml_predictions_total": 800 + index * 33,
                    "ml_predictions_per_30s": ml_predictions_per_30s,
                    "ml_processing_rate_per_30s": round(ml_predictions_per_30s / 30.0, 2),
                    "last_ml_prediction_latency_ms": round(24.0 + (index % 5) * 5.5, 2),
                    "secondary_model_queue_size": 4 + (index % 6),
                    "secondary_model_queue_maxsize": 64,
                    "secondary_model_queue_usage_percent": round(6.0 + (index % 6) * 3.5, 2),
                    "secondary_model_predictions_dropped_total": index // 6,
                    "secondary_model_predictions_total": 500 + index * 19,
                    "secondary_model_predictions_per_30s": 14 + (index % 4) * 2,
                    "application_attribution_available": True,
                    "application_attribution_note": f"{SEED_OWNER_NOTE} snapshot {index:03d}",
                    "active_network_exchanges": active_exchanges,
                },
                created_at=ts,
            )
        )

    for index in range(24):
        bucket_start = (SEED_NOW - timedelta(hours=23 - index)).replace(minute=0, second=0, microsecond=0)
        network_activity_total = 9000 + index * 210
        threat_event_total = 42 + (index % 6) * 5
        blocked_event_total = 8 + (index % 4) * 2
        benign_event_total = max(network_activity_total - threat_event_total, 0)
        rollups.append(
            _stamp(
                {
                    "id": f"seed_network_threat_rollup_{index:03d}",
                    "bucket_start": bucket_start,
                    "bucket_size": "hour",
                    "network_activity_total": network_activity_total,
                    "threat_event_total": threat_event_total,
                    "benign_event_total": benign_event_total,
                    "blocked_event_total": blocked_event_total,
                    "telemetry_snapshot_count": 2,
                    "ml_prediction_total": 60 + index * 4,
                    "active_sessions_peak": 7 + (index % 5),
                    "packet_loss_event_total": 1 if index % 9 == 0 else 0,
                    "threat_rate": round(threat_event_total / network_activity_total, 4),
                },
                created_at=bucket_start,
            )
        )
    return telemetry_rows, rollups


def build_seed_plan() -> SeedPlan:
    users, oauth_accounts, demo_credentials = _build_users()
    auth_sessions, ip_locations = _build_auth_sessions()
    api_keys = _build_api_keys()
    engines = _build_engines()
    network_sessions = _build_network_sessions()
    ids_events = _build_ids_events(network_sessions)
    alerts = _build_alerts(network_sessions, ids_events)
    block_events, engine_commands, ip_control_states = _build_block_events_and_state(network_sessions)
    sql_injection_events = _build_sql_injection_events()
    engine_telemetry_snapshots, network_threat_rollups = _build_engine_telemetry(network_sessions)
    excluded_tables = [
        ExcludedTable(
            table_name="notifications",
            reason="Model exists but current Alembic migration chain does not create this table; model also points to nonexistent `threats` table.",
        )
    ]
    return SeedPlan(
        users=users,
        oauth_accounts=oauth_accounts,
        auth_sessions=auth_sessions,
        ip_locations=ip_locations,
        api_keys=api_keys,
        engines=engines,
        network_sessions=network_sessions,
        ids_events=ids_events,
        alerts=alerts,
        sql_injection_events=sql_injection_events,
        engine_commands=engine_commands,
        block_events=block_events,
        ip_control_states=ip_control_states,
        engine_telemetry_snapshots=engine_telemetry_snapshots,
        network_threat_rollups=network_threat_rollups,
        demo_credentials=demo_credentials,
        excluded_tables=excluded_tables,
    )
