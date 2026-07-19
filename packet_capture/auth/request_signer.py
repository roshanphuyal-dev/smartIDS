"""Engine-side HMAC request signing for internal-service-auth-protected routes.

Mirrors ``backend/app/common/internal_auth.py::verify_internal_signature``
exactly: the signing string is

    f"{METHOD}\\n{path_with_query}\\n{sha256(body).hexdigest()}\\n{timestamp}\\n{nonce}"

HMAC-SHA256'd with the shared secret (``SMARTIDS_INTERNAL_SERVICE_TOKEN``),
hex-encoded. Every engine-side HTTP caller that talks to the backend's
internal-service-auth-protected routes should sign right at the point of
sending, using the exact method/path+query/raw body bytes that go out on
the wire.
"""

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit


def path_with_query(url: str) -> str:
    """Derive ``path`` (plus ``"?"+query`` if present) from a full URL.

    Matches the backend's ``request.url.path`` (+ ``"?"+request.url.query``)
    derivation so the signed string lines up byte-for-byte.
    """
    parts = urlsplit(url)
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


class InternalRequestSigner:
    def __init__(self, secret: str, engine_id: str | None = None):
        self._secret = secret.encode()
        self._engine_id = engine_id

    def sign(self, method: str, path: str, body: bytes) -> dict[str, str]:
        timestamp = str(time.time())
        nonce = secrets.token_hex(16)
        body_hash = hashlib.sha256(body).hexdigest()
        signing_string = f"{method.upper()}\n{path}\n{body_hash}\n{timestamp}\n{nonce}"
        signature = hmac.new(self._secret, signing_string.encode(), hashlib.sha256).hexdigest()
        headers = {
            "x-smartids-signature": signature,
            "x-smartids-timestamp": timestamp,
            "x-smartids-nonce": nonce,
        }
        if self._engine_id:
            headers["x-smartids-engine-id"] = self._engine_id
        return headers
