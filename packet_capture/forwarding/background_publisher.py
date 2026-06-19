from __future__ import annotations

from queue import Full, Queue
from threading import Lock, Thread
from typing import Callable

from packet_capture.utils.logger import IDSLogger, log_event


class BackgroundPublisher:
    def __init__(
        self,
        *,
        name: str,
        publish: Callable[[dict], bool],
        max_queue_size: int = 512,
        drop_log_every: int = 25,
    ) -> None:
        self.name = name
        self._publish = publish
        self._queue: Queue[dict] = Queue(maxsize=max(1, max_queue_size))
        self._drop_log_every = max(1, drop_log_every)
        self._logger = IDSLogger.get_logger(f"forwarding.{name}")
        self._lock = Lock()
        self._dropped = 0
        self._worker = Thread(target=self._run, daemon=True, name=f"smartids-{name}-publisher")
        self._worker.start()

    def submit(self, payload: dict) -> bool:
        try:
            self._queue.put_nowait(payload)
            return True
        except Full:
            with self._lock:
                self._dropped += 1
                dropped = self._dropped
            if dropped == 1 or dropped % self._drop_log_every == 0:
                log_event(
                    self._logger,
                    "warning",
                    "background publisher queue full",
                    {
                        "event_type": "publisher_queue_full",
                        "publisher": self.name,
                        "queue_size": self._queue.qsize(),
                        "queue_maxsize": self._queue.maxsize,
                        "dropped_total": dropped,
                    },
                )
            return False

    def _run(self) -> None:
        while True:
            payload = self._queue.get()
            try:
                self._publish(payload)
            except Exception as exc:
                log_event(
                    self._logger,
                    "warning",
                    "background publisher dispatch failed",
                    {
                        "event_type": "publisher_dispatch_failed",
                        "publisher": self.name,
                        "error": str(exc),
                    },
                )

