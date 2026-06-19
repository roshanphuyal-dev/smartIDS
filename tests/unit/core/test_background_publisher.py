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
        gate.set()
        time.sleep(0.05)
