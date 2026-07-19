import json
import os
from datetime import datetime, timezone
from pathlib import Path


class IPActivityTracker:
    def __init__(
        self,
        file_path: str = "logs/ip_activity.jsonl",
        max_tracked_ips: int | None = None,
        max_action_history: int | None = None,
        max_file_entries: int | None = None,
        file_compaction_interval_records: int | None = None,
    ):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = {}
        self.max_tracked_ips = self._positive_int(
            max_tracked_ips,
            env_name="SMARTIDS_IP_ACTIVITY_MAX_TRACKED_IPS",
            default=10000,
        )
        self.max_action_history = self._positive_int(
            max_action_history,
            env_name="SMARTIDS_IP_ACTIVITY_MAX_ACTION_HISTORY",
            default=25,
        )
        self.max_file_entries = self._positive_int(
            max_file_entries,
            env_name="SMARTIDS_IP_ACTIVITY_MAX_FILE_ENTRIES",
            default=50000,
        )
        self.file_compaction_interval_records = self._positive_int(
            file_compaction_interval_records,
            env_name="SMARTIDS_IP_ACTIVITY_FILE_COMPACTION_INTERVAL_RECORDS",
            default=100,
        )
        self._records_since_compaction = 0

    def record_activity(
        self,
        ip_address: str,
        attack_type: str,
        action: str,
        timestamp: float,
    ):
        now_iso = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
        state = self._state.get(ip_address)

        if state is None:
            state = {
                "ip": ip_address,
                "first_detected_time": now_iso,
                "last_detected_time": now_iso,
                "total_attack_attempts": 0,
                "attack_types_used": set(),
                "action_history": [],
            }
            self._state[ip_address] = state

        state["last_detected_time"] = now_iso
        state["total_attack_attempts"] += 1
        state["attack_types_used"].add(str(attack_type))
        state["action_history"].append(
            {
                "timestamp": now_iso,
                "action": str(action),
                "attack_type": str(attack_type),
            }
        )
        state["action_history"] = state["action_history"][-self.max_action_history :]

        self._prune_state()

        attempt_pattern = "single_attempt"
        if state["total_attack_attempts"] > 1:
            attempt_pattern = "repeated_attempts"

        payload = {
            "ip": ip_address,
            "first_detected_time": state["first_detected_time"],
            "last_detected_time": state["last_detected_time"],
            "total_attack_attempts": state["total_attack_attempts"],
            "attack_types_used": sorted(state["attack_types_used"]),
            "attempt_pattern": attempt_pattern,
            "action_history": state["action_history"][-self.max_action_history :],
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self._records_since_compaction += 1
        self._compact_file_if_needed()

    def snapshot(self) -> list[dict]:
        items = []
        for ip_address, state in self._state.items():
            attempt_pattern = "single_attempt"
            if state["total_attack_attempts"] > 1:
                attempt_pattern = "repeated_attempts"

            items.append(
                {
                    "ip": ip_address,
                    "first_detected_time": state["first_detected_time"],
                    "last_detected_time": state["last_detected_time"],
                    "total_attack_attempts": state["total_attack_attempts"],
                    "attack_types_used": sorted(state["attack_types_used"]),
                    "attempt_pattern": attempt_pattern,
                    "action_history": state["action_history"][-self.max_action_history :],
                }
            )
        return items

    @staticmethod
    def _positive_int(value: int | None, *, env_name: str, default: int) -> int:
        if value is None:
            value = os.getenv(env_name, str(default))
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, parsed)

    def _prune_state(self) -> None:
        overflow = len(self._state) - self.max_tracked_ips
        if overflow <= 0:
            return

        ordered_ips = sorted(
            self._state,
            key=lambda ip_address: self._state[ip_address]["last_detected_time"],
        )
        for ip_address in ordered_ips[:overflow]:
            self._state.pop(ip_address, None)

    def _compact_file_if_needed(self) -> None:
        if self._records_since_compaction < self.file_compaction_interval_records:
            return
        self._records_since_compaction = 0

        try:
            lines = self.file_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return

        if len(lines) <= self.max_file_entries:
            return

        retained = lines[-self.max_file_entries :]
        self.file_path.write_text("\n".join(retained) + "\n", encoding="utf-8")
