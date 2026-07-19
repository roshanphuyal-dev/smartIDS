"""Persistent local storage for a browser-approved engine credential.

Mirrors ``response_engine/processed_command_store.py``'s atomic-write
pattern exactly: write to a ``.tmp`` sibling file, then ``Path.replace()``
onto the real path (atomic on POSIX and Windows), guarded by a
``threading.Lock``. Loading tolerates a missing/corrupt file by returning
``None`` rather than raising, since a failed/absent local config is a normal,
expected state (unregistered engine) not an error condition.
"""

import json
import os
from pathlib import Path
from threading import Lock

DEFAULT_CONFIG_PATH = "./engine_config.json"

_REQUIRED_FIELDS = ("engine_id", "engine_secret", "backend_url", "heartbeat_interval_seconds")


class EngineLocalConfig:
    def __init__(self, file_path: str | None = None) -> None:
        self.file_path = Path(
            file_path or os.getenv("SMARTIDS_ENGINE_CONFIG_PATH", DEFAULT_CONFIG_PATH)
        )
        self._lock = Lock()

    def save(
        self,
        *,
        engine_id: str,
        engine_secret: str,
        backend_url: str,
        heartbeat_interval_seconds: int,
    ) -> None:
        payload = {
            "engine_id": engine_id,
            "engine_secret": engine_secret,
            "backend_url": backend_url,
            "heartbeat_interval_seconds": heartbeat_interval_seconds,
        }
        with self._lock:
            parent = self.file_path.parent
            if str(parent):
                parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
            temp_path.replace(self.file_path)

    def load(self) -> dict | None:
        with self._lock:
            try:
                payload = json.loads(self.file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        if not isinstance(payload, dict):
            return None
        if not all(field in payload for field in _REQUIRED_FIELDS):
            return None
        return payload

    @classmethod
    def load_default(cls) -> dict | None:
        """Convenience for callers that just want "is there a saved config"."""
        return cls().load()
