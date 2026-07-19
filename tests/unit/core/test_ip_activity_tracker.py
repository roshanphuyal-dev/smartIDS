from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from response_engine.ip_activity_tracker import IPActivityTracker


class IPActivityTrackerTest(unittest.TestCase):
    def test_bounds_tracked_ips_by_oldest_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tracker = IPActivityTracker(
                file_path=str(Path(tmp_dir) / "ip_activity.jsonl"),
                max_tracked_ips=2,
            )

            tracker.record_activity("10.0.0.1", "scan", "blocked", 100.0)
            tracker.record_activity("10.0.0.2", "scan", "blocked", 101.0)
            tracker.record_activity("10.0.0.3", "scan", "blocked", 102.0)

            snapshot_ips = {item["ip"] for item in tracker.snapshot()}
            self.assertEqual(snapshot_ips, {"10.0.0.2", "10.0.0.3"})

    def test_caps_per_ip_action_history_in_memory_and_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            activity_path = Path(tmp_dir) / "ip_activity.jsonl"
            tracker = IPActivityTracker(
                file_path=str(activity_path),
                max_action_history=2,
            )

            tracker.record_activity("10.0.0.1", "scan", "blocked", 100.0)
            tracker.record_activity("10.0.0.1", "dos", "blocked", 101.0)
            tracker.record_activity("10.0.0.1", "probe", "allowed", 102.0)

            snapshot = tracker.snapshot()[0]
            self.assertEqual(len(snapshot["action_history"]), 2)
            self.assertEqual(snapshot["action_history"][0]["attack_type"], "dos")

            last_payload = json.loads(activity_path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(len(last_payload["action_history"]), 2)
            self.assertEqual(last_payload["action_history"][1]["attack_type"], "probe")

    def test_compacts_file_backed_log_to_recent_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            activity_path = Path(tmp_dir) / "ip_activity.jsonl"
            tracker = IPActivityTracker(
                file_path=str(activity_path),
                max_file_entries=3,
                file_compaction_interval_records=1,
            )

            for index in range(5):
                tracker.record_activity(f"10.0.0.{index}", "scan", "blocked", 100.0 + index)

            lines = activity_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            retained_ips = [json.loads(line)["ip"] for line in lines]
            self.assertEqual(retained_ips, ["10.0.0.2", "10.0.0.3", "10.0.0.4"])


if __name__ == "__main__":
    unittest.main()
