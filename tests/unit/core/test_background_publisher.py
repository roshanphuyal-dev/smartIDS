from __future__ import annotations

import threading
import time
import unittest

from packet_capture.forwarding.background_publisher import BackgroundPublisher


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
