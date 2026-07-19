import json
from pathlib import Path
from datetime import datetime, timezone


class BlockRecordStore:
    def __init__(self, file_path: str = "logs/blocked_ips.jsonl"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: dict):
        payload = dict(event)
        payload["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()

        with self.file_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=True) + "\n")
