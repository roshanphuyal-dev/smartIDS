"""Bounded, disk-backed spill buffer for a single forwarder.

Used by ``BackgroundPublisher`` to durably hold payloads that fail to
publish (e.g. during a backend outage) instead of dropping them, and to
replay them in order once the backend is reachable again.

Storage format is one JSON object per line (JSONL) in a single file per
publisher. Appends use plain ``open(path, "a")`` + write + flush -- an
append is already atomic-enough at the OS level for this use case, unlike
the single-blob-overwrite pattern used by
``response_engine/processed_command_store.py`` and
``packet_capture/registration/local_config.py``. Full-file rewrites (used
when trimming at capacity, or discarding a delivered prefix) DO follow
those modules' atomic temp-file + ``Path.replace()`` convention, since
those operations really do replace the whole file.

Any line that fails to parse as JSON is treated as corrupt and dropped
(logged, not raised) rather than crashing the engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from packet_capture.utils.logger import IDSLogger, log_event

_TRIM_HYSTERESIS = 1.1  # only compact once 10% past max_entries, not every append


class DiskSpillStore:
    def __init__(self, *, file_path: str, max_entries: int = 2000) -> None:
        self.file_path = Path(file_path)
        self.max_entries = max(1, max_entries)
        self._lock = Lock()
        self._logger = IDSLogger.get_logger("forwarding.disk_spill_store")

        parent = self.file_path.parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            self._count = self._count_lines_locked()

    def append(self, payload: dict) -> None:
        line = json.dumps(payload, ensure_ascii=True)
        with self._lock:
            with open(self.file_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
            self._count += 1
            if self._count > self.max_entries * _TRIM_HYSTERESIS:
                self._compact_locked()

    def peek_batch(self, max_items: int) -> list[dict]:
        if max_items <= 0:
            return []
        with self._lock:
            lines = self._read_lines_locked()

        items: list[dict] = []
        for line in lines:
            if len(items) >= max_items:
                break
            payload = self._decode_line(line)
            if payload is not None:
                items.append(payload)
        return items

    def discard_batch(self, count: int) -> None:
        """Removes the oldest ``count`` *valid* entries (i.e. the same items
        ``peek_batch`` would have returned), together with any corrupt lines
        interspersed among them -- corrupt lines are garbage regardless, so
        they are cleared out alongside the delivered prefix rather than
        left to permanently offset future counts.
        """
        if count <= 0:
            return
        with self._lock:
            lines = self._read_lines_locked()
            valid_seen = 0
            cut_index = len(lines)
            for index, line in enumerate(lines):
                payload = self._decode_line_quiet(line)
                if payload is not None:
                    valid_seen += 1
                    if valid_seen >= count:
                        cut_index = index + 1
                        break
            remaining = lines[cut_index:]
            self._write_lines_locked(remaining)
            self._count = len(remaining)

    def is_empty(self) -> bool:
        with self._lock:
            return self._count <= 0

    def count(self) -> int:
        with self._lock:
            return self._count

    def _decode_line(self, line: str) -> dict | None:
        payload, corrupt = self._try_decode(line)
        if corrupt:
            log_event(
                self._logger,
                "warning",
                "disk spill store dropped corrupt line",
                {
                    "event_type": "disk_spill_corrupt_line",
                    "file_path": str(self.file_path),
                },
            )
        return payload

    def _decode_line_quiet(self, line: str) -> dict | None:
        """Same decoding as ``_decode_line`` but without re-logging -- used
        by ``discard_batch`` when re-walking lines ``peek_batch`` already
        logged a warning for.
        """
        payload, _corrupt = self._try_decode(line)
        return payload

    @staticmethod
    def _try_decode(line: str) -> tuple[dict | None, bool]:
        stripped = line.strip()
        if not stripped:
            return None, False
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return None, True
        if not isinstance(payload, dict):
            return None, True
        return payload, False

    def _read_lines_locked(self) -> list[str]:
        try:
            text = self.file_path.read_text(encoding="utf-8")
        except OSError:
            return []
        return [line for line in text.split("\n") if line.strip()]

    def _write_lines_locked(self, lines: list[str]) -> None:
        temp_path = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        content = "".join(f"{line}\n" for line in lines)
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(self.file_path)

    def _count_lines_locked(self) -> int:
        return len(self._read_lines_locked())

    def _compact_locked(self) -> None:
        lines = self._read_lines_locked()
        trimmed = lines[-self.max_entries :]
        self._write_lines_locked(trimmed)
        self._count = len(trimmed)
