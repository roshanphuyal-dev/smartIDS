"""Orchestrates browser-based engine registration (Part A Phase 1).

Steps, per docs/plans/engine-registration-and-capture-filter.md's
"Registration protocol" section:

1. Generate ``registration_id = secrets.token_urlsafe(24)``.
2. Start a temporary loopback HTTP server (``registration_server.py``) to
   receive the approved credential.
3. ``POST {backend_url}/api/v1/engines/register/init`` -- unauthenticated,
   just lets the backend show pending metadata to the user.
4. ``webbrowser.open(...)`` to the dashboard's approval page.
5. Block (bounded by the temp server's own ~10 minute timeout) waiting for
   the dashboard to relay the approved credential to the temp server.
6. On success, persist the credential via ``local_config.py``.
7. On failure/timeout, log a warning and return ``None`` -- packet capture
   must never depend on backend/browser availability, so this never raises
   and never blocks startup beyond the bounded timeout.
"""

import json
import os
import platform
import secrets
import webbrowser
from urllib import error, request

from packet_capture.registration.local_config import EngineLocalConfig
from packet_capture.registration.registration_server import (
    DEFAULT_TIMEOUT_SECONDS,
    RegistrationServer,
)
from packet_capture.utils.logger import IDSLogger, log_event

# No existing version constant was found anywhere in the repo (no
# __version__, VERSION file, or pyproject.toml) -- literal placeholder.
ENGINE_VERSION = "0.1.0"

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30

# SMARTIDS_BACKEND_BASE_URL already exists as a precedent (written by
# script/start-ids.sh into .smartids-runtime.env), so it's reused here
# rather than inventing a second backend-URL env var. No frontend-URL env
# var precedent exists anywhere in the repo (the dashboard's own port is
# hardcoded in start-ids.sh), so SMARTIDS_FRONTEND_URL is a new name.
DEFAULT_BACKEND_URL = "http://127.0.0.1:3100"
DEFAULT_FRONTEND_URL = "http://127.0.0.1:3000"


def run_registration(
    *,
    backend_url: str | None = None,
    frontend_url: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict | None:
    """Runs the full registration flow, blocking until completion or timeout.

    Returns the saved local-config payload (``engine_id``, ``engine_secret``,
    ``backend_url``, ``heartbeat_interval_seconds``) on success, or ``None``
    on any failure. Never raises -- callers should treat ``None`` as "stay
    in whatever fallback auth mode was already in effect".
    """
    logger = IDSLogger.get_logger("registration.client")

    backend_url = (backend_url or os.getenv("SMARTIDS_BACKEND_BASE_URL", DEFAULT_BACKEND_URL)).strip().rstrip("/")
    frontend_url = (frontend_url or os.getenv("SMARTIDS_FRONTEND_URL", DEFAULT_FRONTEND_URL)).strip().rstrip("/")

    registration_id = secrets.token_urlsafe(24)
    server = RegistrationServer(registration_id, timeout_seconds=timeout_seconds)

    try:
        server.start()
    except OSError as exc:
        log_event(
            logger,
            "warning",
            "engine registration failed to start local callback server",
            {"event_type": "engine_registration_server_start_failed", "error": str(exc)},
        )
        return None

    try:
        if not _post_register_init(
            backend_url=backend_url,
            registration_id=registration_id,
            logger=logger,
        ):
            return None

        approval_url = (
            f"{frontend_url}/engines/register"
            f"?registration_id={registration_id}&callback_port={server.port}"
        )
        try:
            webbrowser.open(approval_url)
        except Exception as exc:  # pragma: no cover - best effort, never fatal
            log_event(
                logger,
                "warning",
                "engine registration could not open browser automatically",
                {
                    "event_type": "engine_registration_browser_open_failed",
                    "error": str(exc),
                    "approval_url": approval_url,
                },
            )

        log_event(
            logger,
            "info",
            "engine registration waiting for browser approval",
            {"event_type": "engine_registration_waiting", "approval_url": approval_url},
        )

        result = server.wait_for_completion(timeout=timeout_seconds + 5)
        if not result:
            log_event(
                logger,
                "warning",
                "engine registration timed out or failed, continuing unregistered",
                {"event_type": "engine_registration_incomplete", "registration_id": registration_id},
            )
            return None

        return _persist_result(result, fallback_backend_url=backend_url, logger=logger)
    finally:
        server.shutdown()


def _persist_result(result: dict, *, fallback_backend_url: str, logger) -> dict | None:
    engine_id = str(result.get("engine_id", "")).strip()
    engine_secret = str(result.get("engine_secret", "")).strip()
    resolved_backend_url = str(result.get("backend_url") or fallback_backend_url).strip()

    if not engine_id or not engine_secret:
        log_event(
            logger,
            "warning",
            "engine registration completed with an invalid payload, ignoring",
            {"event_type": "engine_registration_invalid_payload"},
        )
        return None

    try:
        heartbeat_interval_seconds = int(
            result.get("heartbeat_interval_seconds", DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
        )
    except (TypeError, ValueError):
        heartbeat_interval_seconds = DEFAULT_HEARTBEAT_INTERVAL_SECONDS

    config = EngineLocalConfig()
    config.save(
        engine_id=engine_id,
        engine_secret=engine_secret,
        backend_url=resolved_backend_url,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )

    log_event(
        logger,
        "info",
        "engine registration completed and local config saved",
        {"event_type": "engine_registration_completed", "engine_id": engine_id},
    )
    return config.load()


def _post_register_init(*, backend_url: str, registration_id: str, logger) -> bool:
    body = json.dumps(
        {
            "registrationId": registration_id,
            "hostname": platform.node(),
            "osName": platform.system(),
            "version": ENGINE_VERSION,
        }
    ).encode("utf-8")

    req = request.Request(
        url=f"{backend_url}/api/v1/engines/register/init",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5.0) as response:
            return 200 <= int(response.status) < 300
    except (error.URLError, TimeoutError, ValueError, OSError) as exc:
        log_event(
            logger,
            "warning",
            "engine registration init call to backend failed",
            {"event_type": "engine_registration_init_failed", "error": str(exc)},
        )
        return False
