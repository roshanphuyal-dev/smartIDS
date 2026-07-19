import json
from urllib import error, request

from packet_capture.auth.request_signer import InternalRequestSigner, path_with_query


class FastAPISessionUpdateForwarder:
    def __init__(
        self,
        endpoint_url: str,
        timeout_seconds: float = 2.0,
        signer: InternalRequestSigner | None = None,
    ):
        self.endpoint_url = endpoint_url
        self.timeout_seconds = timeout_seconds
        self._signer = signer

    def publish_session_update(self, session_update: dict) -> bool:
        payload = json.dumps(session_update).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._signer is not None:
            headers.update(self._signer.sign("POST", path_with_query(self.endpoint_url), payload))

        req = request.Request(
            url=self.endpoint_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return 200 <= int(response.status) < 300
        except (error.URLError, TimeoutError, ValueError):
            return False
