from __future__ import annotations

import threading
import time
import unittest

from packet_capture.forwarding.background_publisher import BackgroundPublisher


class FakeSpillStore:
    """In-memory stand-in for ``DiskSpillStore`` so these tests exercise
    ``BackgroundPublisher``'s wiring (when it spills, drains, and what it
    discards) without depending on real disk I/O or its own test coverage.
    """

    def __init__(self, initial: list[dict] | None = None) -> None:
        self.items: list[dict] = list(initial or [])
        self.appended: list[dict] = []
        self.discard_calls: list[int] = []

    def append(self, payload: dict) -> None:
        self.items.append(payload)
        self.appended.append(payload)

    def peek_batch(self, max_items: int) -> list[dict]:
        return list(self.items[:max_items])

    def discard_batch(self, count: int) -> None:
        self.discard_calls.append(count)
        del self.items[:count]

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def count(self) -> int:
        return len(self.items)


class BackgroundPublisherTest(unittest.TestCase):
    def test_submit_dispatches_payload_without_blocking_caller(self) -> None:
        received: list[dict] = []
        done = threading.Event()

        def publish(payload: dict) -> bool:
            received.append(payload)
            done.set()
            return True

        publisher = BackgroundPublisher(
            name="test",
            publish=publish,
            max_queue_size=4,
        )

        self.assertTrue(publisher.submit({"value": 1}))
        self.assertTrue(done.wait(timeout=1.0))
        self.assertEqual(received, [{"value": 1}])

    def test_submit_drops_when_queue_is_full(self) -> None:
        gate = threading.Event()

        def publish(_payload: dict) -> bool:
            gate.wait(timeout=1.0)
            return True

        publisher = BackgroundPublisher(
            name="test",
            publish=publish,
            max_queue_size=1,
        )

        self.assertTrue(publisher.submit({"value": 1}))
        self.assertFalse(publisher.submit({"value": 2}))
        self.assertEqual(publisher.dropped_total(), 1)
        gate.set()
        time.sleep(0.05)

    def test_queue_size_and_maxsize_accessors_report_depth(self) -> None:
        gate = threading.Event()

        def publish(_payload: dict) -> bool:
            gate.wait(timeout=1.0)
            return True

        publisher = BackgroundPublisher(
            name="test",
            publish=publish,
            max_queue_size=4,
        )

        self.assertEqual(publisher.queue_maxsize(), 4)
        self.assertTrue(publisher.submit({"value": 1}))
        # One item is immediately picked up by the worker, but the accessor
        # must never raise even while a publish is in-flight or the queue
        # is empty.
        self.assertGreaterEqual(publisher.queue_size(), 0)
        self.assertEqual(publisher.dropped_total(), 0)
        gate.set()
        time.sleep(0.05)

    def test_worker_count_spawns_multiple_worker_threads(self) -> None:
        def publish(_payload: dict) -> bool:
            return True

        publisher = BackgroundPublisher(
            name="test-multi",
            publish=publish,
            max_queue_size=16,
            worker_count=3,
        )

        self.assertEqual(len(publisher._workers), 3)
        for worker in publisher._workers:
            self.assertTrue(worker.is_alive())
            self.assertTrue(worker.daemon)

    def test_worker_count_processes_concurrent_items_with_multiple_workers(self) -> None:
        received: list[int] = []
        lock = threading.Lock()
        all_received = threading.Event()
        release_gates: dict[int, threading.Event] = {}

        def publish(payload: dict) -> bool:
            value = payload["value"]
            gate = release_gates[value]
            gate.wait(timeout=1.0)
            with lock:
                received.append(value)
                if len(received) == 3:
                    all_received.set()
            return True

        for value in range(3):
            release_gates[value] = threading.Event()

        publisher = BackgroundPublisher(
            name="test-multi-concurrent",
            publish=publish,
            max_queue_size=16,
            worker_count=3,
        )

        for value in range(3):
            self.assertTrue(publisher.submit({"value": value}))

        # Give all three workers a chance to pick up an item concurrently before
        # releasing them, proving a single worker is not serializing the queue.
        time.sleep(0.1)
        for gate in release_gates.values():
            gate.set()

        self.assertTrue(all_received.wait(timeout=1.0))
        self.assertEqual(sorted(received), [0, 1, 2])

    def test_default_behavior_unchanged_when_no_spill_store_configured(self) -> None:
        """The single most important regression test here: with
        spill_store omitted (the default, and what almost every real
        deployment runs with), a failed publish must still be discarded
        exactly like it was before disk spilling existed -- no durable
        buffering, no crash, no double-dispatch.
        """
        calls: list[dict] = []
        lock = threading.Lock()
        done = threading.Event()

        def publish(payload: dict) -> bool:
            with lock:
                calls.append(payload)
                if len(calls) == 2:
                    done.set()
            return False  # simulate a backend outage: every publish fails

        publisher = BackgroundPublisher(
            name="test-no-spill",
            publish=publish,
            max_queue_size=4,
        )

        self.assertIsNone(publisher._spill_store)
        self.assertTrue(publisher.submit({"value": 1}))
        self.assertTrue(publisher.submit({"value": 2}))
        self.assertTrue(done.wait(timeout=1.0))
        time.sleep(0.05)

        self.assertEqual(calls, [{"value": 1}, {"value": 2}])
        self.assertEqual(publisher.spill_backlog_count(), 0)

    def test_failing_publish_spills_payload_when_spill_store_configured(self) -> None:
        spill_store = FakeSpillStore()

        def publish(_payload: dict) -> bool:
            return False

        publisher = BackgroundPublisher(
            name="test-spill",
            publish=publish,
            max_queue_size=4,
            spill_store=spill_store,
        )

        self.assertTrue(publisher.submit({"value": 1}))

        deadline = time.time() + 1.0
        while time.time() < deadline and not spill_store.appended:
            time.sleep(0.01)

        self.assertEqual(spill_store.appended, [{"value": 1}])

    def test_successful_publish_drains_spill_backlog_in_order(self) -> None:
        spill_store = FakeSpillStore(initial=[{"value": "old-1"}, {"value": "old-2"}])
        published_order: list[dict] = []
        lock = threading.Lock()

        def publish(payload: dict) -> bool:
            with lock:
                published_order.append(payload)
            return True

        publisher = BackgroundPublisher(
            name="test-drain",
            publish=publish,
            max_queue_size=4,
            spill_store=spill_store,
        )

        self.assertTrue(publisher.submit({"value": "live"}))

        deadline = time.time() + 1.0
        while time.time() < deadline and spill_store.count() > 0:
            time.sleep(0.01)

        self.assertEqual(
            published_order,
            [{"value": "live"}, {"value": "old-1"}, {"value": "old-2"}],
        )
        self.assertEqual(spill_store.discard_calls, [2])
        self.assertTrue(spill_store.is_empty())

    def test_partial_failure_mid_drain_leaves_correct_remainder_spilled(self) -> None:
        spill_store = FakeSpillStore(
            initial=[{"value": "old-1"}, {"value": "old-2"}, {"value": "old-3"}]
        )
        published_order: list[dict] = []
        lock = threading.Lock()

        def publish(payload: dict) -> bool:
            with lock:
                published_order.append(payload)
            # old-2 fails to deliver; the drain must stop there and must
            # not skip ahead to old-3, preserving chronological order.
            return payload.get("value") != "old-2"

        publisher = BackgroundPublisher(
            name="test-partial-drain",
            publish=publish,
            max_queue_size=4,
            spill_store=spill_store,
        )

        self.assertTrue(publisher.submit({"value": "live"}))

        deadline = time.time() + 1.0
        while time.time() < deadline and len(published_order) < 3:
            time.sleep(0.01)
        time.sleep(0.05)  # let discard_batch settle after the mid-drain failure

        self.assertEqual(
            published_order,
            [{"value": "live"}, {"value": "old-1"}, {"value": "old-2"}],
        )
        self.assertEqual(spill_store.discard_calls, [1])
        self.assertEqual(spill_store.items, [{"value": "old-2"}, {"value": "old-3"}])

    def test_spill_backlog_count_delegates_to_configured_store(self) -> None:
        spill_store = FakeSpillStore(initial=[{"a": 1}, {"a": 2}])

        def publish(_payload: dict) -> bool:
            return True

        publisher = BackgroundPublisher(
            name="test-backlog-count",
            publish=publish,
            spill_store=spill_store,
        )

        # Nothing has been submitted, so the drain path never triggers and
        # the backlog is untouched -- safe to assert without a timing race.
        self.assertEqual(publisher.spill_backlog_count(), 2)

    def test_spill_backlog_count_is_zero_without_configured_store(self) -> None:
        def publish(_payload: dict) -> bool:
            return True

        publisher = BackgroundPublisher(name="test-no-backlog", publish=publish)

        self.assertEqual(publisher.spill_backlog_count(), 0)
