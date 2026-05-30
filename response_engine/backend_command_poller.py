import json
import time
from urllib import error, request


class BackendCommandPoller:
    def __init__(self, endpoint_url: str, timeout_seconds: float = 2.0):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    def poll_commands(self) -> list[dict]:
        req = request.Request(url=self.endpoint_url, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if int(response.status) < 200 or int(response.status) >= 300:
                    return []
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return []

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            commands = payload.get("commands", [])
            if isinstance(commands, list):
                return [item for item in commands if isinstance(item, dict)]

        return []

    def ack_command(self, ack_endpoint_url: str, command_id: str, status: str) -> bool:
        payload = json.dumps(
            {
                "command_id": command_id,
                "status": status,
                "acked_at": time.time(),
            }
        ).encode("utf-8")
        req = request.Request(
            url=ack_endpoint_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return 200 <= int(response.status) < 300
        except (error.URLError, TimeoutError, ValueError):
            return False
