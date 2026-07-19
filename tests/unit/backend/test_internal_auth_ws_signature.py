from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/testdb")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "http://127.0.0.1:3000")

from app.common.internal_auth import check_and_consume_nonce, verify_internal_ws_signature
from app.features.realtime.engine_ws_schemas import ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH
from packet_capture.auth.request_signer import InternalRequestSigner
from packet_capture.realtime.engine_ws_client import (
    ENGINE_WS_AUTH_METHOD as ENGINE_SIDE_AUTH_METHOD,
    ENGINE_WS_AUTH_PATH as ENGINE_SIDE_AUTH_PATH,
)


class FakeAsyncRedis:
    """Minimal in-memory stand-in for redis.asyncio.Redis's SET NX EX usage."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, name: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and name in self._store:
            return None
        self._store[name] = value
        return True


class CheckAndConsumeNonceTest(unittest.TestCase):
    def test_first_use_is_accepted(self) -> None:
        redis_client = FakeAsyncRedis()
        self.assertTrue(asyncio.run(check_and_consume_nonce(redis_client, "nonce-a")))

    def test_replay_is_rejected(self) -> None:
        redis_client = FakeAsyncRedis()
        asyncio.run(check_and_consume_nonce(redis_client, "nonce-b"))
        self.assertFalse(asyncio.run(check_and_consume_nonce(redis_client, "nonce-b")))


class VerifyInternalWSSignatureTest(unittest.TestCase):
    """Verifies the WS handshake using the engine's real signer, proving the
    ENGINE_WS_AUTH_METHOD/PATH stand-in convention lines up byte-for-byte
    between the two independently-implemented sides."""

    def test_valid_signature_from_engine_signer_is_accepted(self) -> None:
        secret = "shared-test-secret"
        signer = InternalRequestSigner(secret)
        headers = signer.sign(ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH, b"")
        redis_client = FakeAsyncRedis()

        result = asyncio.run(
            verify_internal_ws_signature(
                secret=secret,
                method=ENGINE_WS_AUTH_METHOD,
                path=ENGINE_WS_AUTH_PATH,
                body=b"",
                timestamp=headers["x-smartids-timestamp"],
                nonce=headers["x-smartids-nonce"],
                signature=headers["x-smartids-signature"],
                redis_client=redis_client,
            )
        )
        self.assertTrue(result)

    def test_wrong_secret_is_rejected(self) -> None:
        signer = InternalRequestSigner("right-secret")
        headers = signer.sign(ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH, b"")
        redis_client = FakeAsyncRedis()

        result = asyncio.run(
            verify_internal_ws_signature(
                secret="wrong-secret",
                method=ENGINE_WS_AUTH_METHOD,
                path=ENGINE_WS_AUTH_PATH,
                body=b"",
                timestamp=headers["x-smartids-timestamp"],
                nonce=headers["x-smartids-nonce"],
                signature=headers["x-smartids-signature"],
                redis_client=redis_client,
            )
        )
        self.assertFalse(result)

    def test_replayed_nonce_is_rejected_on_second_verification(self) -> None:
        secret = "shared-test-secret"
        signer = InternalRequestSigner(secret)
        headers = signer.sign(ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH, b"")
        redis_client = FakeAsyncRedis()

        kwargs = dict(
            secret=secret,
            method=ENGINE_WS_AUTH_METHOD,
            path=ENGINE_WS_AUTH_PATH,
            body=b"",
            timestamp=headers["x-smartids-timestamp"],
            nonce=headers["x-smartids-nonce"],
            signature=headers["x-smartids-signature"],
            redis_client=redis_client,
        )

        self.assertTrue(asyncio.run(verify_internal_ws_signature(**kwargs)))
        self.assertFalse(asyncio.run(verify_internal_ws_signature(**kwargs)))

    def test_expired_timestamp_is_rejected(self) -> None:
        secret = "shared-test-secret"
        signer = InternalRequestSigner(secret)
        headers = signer.sign(ENGINE_WS_AUTH_METHOD, ENGINE_WS_AUTH_PATH, b"")
        redis_client = FakeAsyncRedis()

        stale_timestamp = str(float(headers["x-smartids-timestamp"]) - 120)

        result = asyncio.run(
            verify_internal_ws_signature(
                secret=secret,
                method=ENGINE_WS_AUTH_METHOD,
                path=ENGINE_WS_AUTH_PATH,
                body=b"",
                timestamp=stale_timestamp,
                nonce=headers["x-smartids-nonce"],
                signature=headers["x-smartids-signature"],
                redis_client=redis_client,
            )
        )
        self.assertFalse(result)


class WSAuthConstantCrossRepoContractTest(unittest.TestCase):
    """The engine and backend each define their own copy of the WS auth
    handshake's stand-in method/path (no HTTP request exists during a WS
    handshake to sign, so a fixed string is signed instead — see both
    modules' docstrings). Nothing else ties the two copies together, so a
    future edit to one side alone would pass both test suites in isolation
    while breaking real cross-process auth. This test runs in the one place
    both packages are importable together (repo-root pytest) and fails loudly
    if they ever diverge.
    """

    def test_engine_and_backend_auth_constants_match(self) -> None:
        self.assertEqual(ENGINE_SIDE_AUTH_METHOD, ENGINE_WS_AUTH_METHOD)
        self.assertEqual(ENGINE_SIDE_AUTH_PATH, ENGINE_WS_AUTH_PATH)


if __name__ == "__main__":
    unittest.main()
