import json
from datetime import datetime, timezone
from pathlib import Path


class IPActivityTracker:
    def __init__(self, file_path: str = "logs/ip_activity.jsonl"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = {}

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
            "action_history": state["action_history"][-25:],
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }

        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=True) + "\n")

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
                    "action_history": state["action_history"][-25:],
                }
            )
        return items
