from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from packet_capture.forwarding.disk_spill_store import DiskSpillStore


class DiskSpillStoreTest(unittest.TestCase):
    def test_append_peek_discard_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = DiskSpillStore(file_path=str(Path(tmp_dir) / "spill.jsonl"))

            self.assertTrue(store.is_empty())
            self.assertEqual(store.count(), 0)

            store.append({"id": 1})
            store.append({"id": 2})
            store.append({"id": 3})

            self.assertFalse(store.is_empty())
            self.assertEqual(store.count(), 3)

            batch = store.peek_batch(2)
            self.assertEqual(batch, [{"id": 1}, {"id": 2}])
            # peek must not remove anything.
            self.assertEqual(store.count(), 3)

            store.discard_batch(2)
            self.assertEqual(store.count(), 1)
            self.assertEqual(store.peek_batch(10), [{"id": 3}])

            store.discard_batch(1)
            self.assertTrue(store.is_empty())

    def test_corrupt_line_is_skipped_and_logged_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "spill.jsonl"
            store = DiskSpillStore(file_path=str(file_path))
            store.append({"id": 1})

            with open(file_path, "a", encoding="utf-8") as handle:
                handle.write("{not valid json\n")

            store.append({"id": 2})

            # peek_batch tolerates the corrupt line -- read/parsed straight
            # from disk, unlike count() (an in-memory counter maintained
            # only via append()/discard_batch()) -- and returns only the
            # valid entries, without raising.
            batch = store.peek_batch(10)
            self.assertEqual(batch, [{"id": 1}, {"id": 2}])

    def test_discard_batch_clears_corrupt_lines_interspersed_with_valid_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "spill.jsonl"
            store = DiskSpillStore(file_path=str(file_path))
            store.append({"id": 1})
            with open(file_path, "a", encoding="utf-8") as handle:
                handle.write("{broken\n")
            store.append({"id": 2})
            store.append({"id": 3})

            # Discard the first two *valid* entries (id=1, id=2); the
            # corrupt line sits between them and should be swept away too.
            store.discard_batch(2)

            self.assertEqual(store.peek_batch(10), [{"id": 3}])

    def test_compaction_trims_to_max_entries_once_past_hysteresis_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = DiskSpillStore(
                file_path=str(Path(tmp_dir) / "spill.jsonl"),
                max_entries=10,
            )

            # Hysteresis is max_entries * 1.1 == 11, so compaction should not
            # trigger until strictly after the 11th append.
            for i in range(11):
                store.append({"id": i})
            self.assertEqual(store.count(), 11)

            store.append({"id": 11})
            # Compacted down to the newest max_entries (10) lines: ids 2..11.
            self.assertEqual(store.count(), 10)
            batch = store.peek_batch(10)
            self.assertEqual([item["id"] for item in batch], list(range(2, 12)))

    def test_constructor_counts_existing_lines_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "spill.jsonl"
            first = DiskSpillStore(file_path=str(file_path))
            first.append({"id": 1})
            first.append({"id": 2})

            second = DiskSpillStore(file_path=str(file_path))
            self.assertEqual(second.count(), 2)

    def test_discard_batch_zero_or_negative_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = DiskSpillStore(file_path=str(Path(tmp_dir) / "spill.jsonl"))
            store.append({"id": 1})
            store.discard_batch(0)
            store.discard_batch(-1)
            self.assertEqual(store.count(), 1)


if __name__ == "__main__":
    unittest.main()
