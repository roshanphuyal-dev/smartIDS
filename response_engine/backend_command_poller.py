import json
import time
from urllib import error, request

from packet_capture.auth.request_signer import InternalRequestSigner, path_with_query


class BackendCommandPoller:
    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = 2.0,
        signer: InternalRequestSigner | None = None,
    ):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self._signer = signer

    def poll_commands(self) -> list[dict]:
        headers = {}
        if self._signer is not None:
            headers.update(self._signer.sign("GET", path_with_query(self.endpoint_url), b""))

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
        if self._signer is not None:
            headers.update(self._signer.sign("POST", path_with_query(ack_endpoint_url), payload))

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
