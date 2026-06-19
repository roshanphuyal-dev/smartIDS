import json
import time
from urllib import error, request


class BackendCommandPoller:
    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = 2.0,
        internal_service_token: str = "",
    ):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self.internal_service_token = internal_service_token.strip()

    def poll_commands(self) -> list[dict]:
        headers = {}
        if self.internal_service_token:
            headers["x-smartids-internal-token"] = self.internal_service_token

        req = request.Request(url=self.endpoint_url, method="GET", headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if int(response.status) < 200 or int(response.status) >= 300:
                    return []
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
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
        headers = {"Content-Type": "application/json"}
        if self.internal_service_token:
            headers["x-smartids-internal-token"] = self.internal_service_token

        req = request.Request(
            url=ack_endpoint_url,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return 200 <= int(response.status) < 300
        except (error.URLError, TimeoutError, ValueError, OSError):
            return False
