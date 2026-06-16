import json
import os
from pathlib import Path
from threading import Lock


class ProcessedCommandStore:
    def __init__(
        self,
        file_path: str = "logs/processed_engine_commands.json",
        max_command_ids: int | None = None,
    ) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_command_ids = self._positive_int(
            max_command_ids,
            env_name="SMARTIDS_PROCESSED_COMMAND_MAX_IDS",
            default=10000,
        )
        self._lock = Lock()
        self._command_ids = self._load()

    def contains(self, command_id: str) -> bool:
        normalized = self._normalize(command_id)
        if not normalized:
            return False
        with self._lock:
            return normalized in self._command_ids

    def add(self, command_id: str) -> None:
        normalized = self._normalize(command_id)
        if not normalized:
            return
        with self._lock:
            if normalized in self._command_ids:
                return
            self._command_ids.append(normalized)
            self._command_ids = self._command_ids[-self.max_command_ids :]
            self._save()

    @staticmethod
    def _normalize(command_id: str) -> str:
        return str(command_id or "").strip()

    @staticmethod
    def _positive_int(value: int | None, *, env_name: str, default: int) -> int:
        if value is None:
            value = os.getenv(env_name, str(default))
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, parsed)

    def _load(self) -> list[str]:
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, dict):
            values = payload.get("command_ids", [])
        else:
            values = []

        command_ids = []
        seen = set()
        for value in values:
            command_id = self._normalize(value)
            if command_id and command_id not in seen:
                command_ids.append(command_id)
                seen.add(command_id)
        return command_ids[-self.max_command_ids :]

    def _save(self) -> None:
        payload = {"command_ids": self._command_ids}
        temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        temp_path.replace(self.file_path)
