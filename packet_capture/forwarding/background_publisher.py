from __future__ import annotations

from queue import Full, Queue
from threading import Lock, Thread
from typing import Callable

from packet_capture.forwarding.disk_spill_store import DiskSpillStore
from packet_capture.utils.logger import IDSLogger, log_event

# One live success drains at most this many spilled items synchronously
# before returning to normal queue processing, so a big backlog doesn't
# starve freshly-submitted, still-live payloads.
_SPILL_DRAIN_BATCH_SIZE = 50


class BackgroundPublisher:
    def __init__(
        self,
        *,
        name: str,
        publish: Callable[[dict], bool],
        max_queue_size: int = 512,
        drop_log_every: int = 25,
        worker_count: int = 1,
        spill_store: DiskSpillStore | None = None,
    ) -> None:
        self.name = name
        self._publish = publish
        self._queue: Queue[dict] = Queue(maxsize=max(1, max_queue_size))
        self._drop_log_every = max(1, drop_log_every)
        self._logger = IDSLogger.get_logger(f"forwarding.{name}")
        self._lock = Lock()
        self._dropped = 0
        self._spill_store = spill_store
        self._worker_count = max(1, worker_count)
        self._workers: list[Thread] = []
        for index in range(self._worker_count):
            worker_name = (
                f"smartids-{name}-publisher" if self._worker_count == 1 else f"smartids-{name}-publisher-{index}"
            )
            worker = Thread(target=self._run, daemon=True, name=worker_name)
            worker.start()
            self._workers.append(worker)
        self._worker = self._workers[0]

    def queue_size(self) -> int:
        try:
            return int(self._queue.qsize())
        except NotImplementedError:
            return 0

    def queue_maxsize(self) -> int:
        return int(self._queue.maxsize)

    def dropped_total(self) -> int:
        with self._lock:
            return self._dropped

    def spill_backlog_count(self) -> int:
        if self._spill_store is None:
            return 0
        return self._spill_store.count()

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
            delivered = False
            try:
                delivered = bool(self._publish(payload))
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

            if not delivered:
                if self._spill_store is not None:
                    self._spill_store.append(payload)
                continue

            if self._spill_store is not None and not self._spill_store.is_empty():
                self._drain_spill_backlog()

    def _drain_spill_backlog(self) -> None:
        """Replays spilled payloads, oldest first, after a live publish
        succeeds. Stops at the first failure (network error, HTTP error, or
        exception) to preserve chronological delivery order -- only the
        confirmed-delivered prefix is discarded from disk; everything from
        the first failure onward (including not-yet-attempted items in this
        batch) stays spilled for the next opportunity.
        """
        assert self._spill_store is not None
        batch = self._spill_store.peek_batch(_SPILL_DRAIN_BATCH_SIZE)
        delivered_count = 0
        for item in batch:
            try:
                ok = bool(self._publish(item))
            except Exception as exc:
                log_event(
                    self._logger,
                    "warning",
                    "background publisher spill replay failed",
                    {
                        "event_type": "publisher_spill_replay_failed",
                        "publisher": self.name,
                        "error": str(exc),
                    },
                )
                break
            if not ok:
                break
            delivered_count += 1

        if delivered_count > 0:
            self._spill_store.discard_batch(delivered_count)

