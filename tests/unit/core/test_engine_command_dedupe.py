from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from packet_capture.processor.packet_processor import PacketProcessor
from response_engine.processed_command_store import ProcessedCommandStore


class FakeAutoBlocker:
    def __init__(self) -> None:
        self.block_calls = 0

    def manual_block(self, *, ip_address: str, duration_seconds: int) -> tuple[bool, str]:
        self.block_calls += 1
        return True, "blocked"


def make_processor(store: ProcessedCommandStore, blocker: FakeAutoBlocker) -> PacketProcessor:
    processor = PacketProcessor.__new__(PacketProcessor)
    processor.auto_blocker = blocker
    processor.processed_command_store = store
    processor.block_event_publisher = None
    return processor


class EngineCommandDedupeTest(unittest.TestCase):
    def test_processed_command_ids_survive_processor_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = Path(tmp_dir) / "processed_commands.json"
            first_store = ProcessedCommandStore(file_path=str(store_path))
            first_blocker = FakeAutoBlocker()
            first_processor = make_processor(first_store, first_blocker)

            ok, status = first_processor.apply_backend_command(
                {
                    "command_id": "cmd-1",
                    "action": "block",
                    "ip_address": "203.0.113.10",
                    "duration_seconds": 300,
                }
            )

            self.assertTrue(ok)
            self.assertEqual(status, "blocked")
            self.assertEqual(first_blocker.block_calls, 1)

            restarted_store = ProcessedCommandStore(file_path=str(store_path))
            restarted_blocker = FakeAutoBlocker()
            restarted_processor = make_processor(restarted_store, restarted_blocker)

            ok, status = restarted_processor.apply_backend_command(
                {
                    "command_id": "cmd-1",
                    "action": "block",
                    "ip_address": "203.0.113.10",
                    "duration_seconds": 300,
                }
            )

            self.assertTrue(ok)
            self.assertEqual(status, "duplicate_command")
            self.assertEqual(restarted_blocker.block_calls, 0)


if __name__ == "__main__":
    unittest.main()
