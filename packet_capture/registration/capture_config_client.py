"""Engine-side fetch of the dashboard-configured capture listen port.

Mirrors ``response_engine/backend_command_poller.py``'s plain ``urllib`` GET
pattern exactly -- no new HTTP dependency. Best-effort: any failure (network,
timeout, malformed response) just means "no remote port configured", and
never blocks capture startup.
"""

import json
from urllib import error, request

from packet_capture.auth.request_signer import InternalRequestSigner, path_with_query


def fetch_capture_watch_port(
    backend_url: str,
    signer: InternalRequestSigner,
    timeout_seconds: float = 2.0,
) -> int | None:
    endpoint_url = backend_url.rstrip("/") + "/api/v1/engines/me/capture-config"
    headers = signer.sign("GET", path_with_query(endpoint_url), b"")

    req = request.Request(url=endpoint_url, method="GET", headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            if int(response.status) < 200 or int(response.status) >= 300:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None

    port = data.get("captureWatchPort")
    return port if isinstance(port, int) else None
