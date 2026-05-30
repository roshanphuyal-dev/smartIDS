import json
from urllib import error, request


class FastAPIIDSEventForwarder:
    def __init__(self, endpoint_url: str, timeout_seconds: float = 2.0):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds

    def publish_event(self, event: dict) -> bool:
        payload = json.dumps(event).encode("utf-8")
        req = request.Request(
            url=self.endpoint_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return 200 <= int(response.status) < 300
        except (error.URLError, TimeoutError, ValueError):
            return False
