import json
from urllib import request, error


class FastAPIAlertForwarder:
    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = 2.0,
        internal_service_token: str = "",
    ):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self.internal_service_token = internal_service_token.strip()

    def publish_alert(self, alert: dict) -> bool:
        payload = json.dumps(alert).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.internal_service_token:
            headers["x-smartids-internal-token"] = self.internal_service_token

        req = request.Request(
            url=self.endpoint_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return 200 <= int(response.status) < 300
        except (error.URLError, TimeoutError, ValueError, OSError):
            return False
