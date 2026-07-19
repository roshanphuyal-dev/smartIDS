from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock

from packet_capture.auth.request_signer import InternalRequestSigner
from packet_capture.realtime.engine_ws_client import (
    ENGINE_WS_AUTH_METHOD,
    ENGINE_WS_AUTH_PATH,
    EngineWSAuthError,
    EngineWSClient,
)


class FakeWebSocket:
    def __init__(self, recv_queue=None):
        self.sent: list[str] = []
        self._recv_queue = list(recv_queue or [])

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        if not self._recv_queue:
            raise AssertionError("FakeWebSocket.recv() called with nothing queued")
        return self._recv_queue.pop(0)


class FakeAckPublisher:
    def __init__(self, submit_result: bool = True) -> None:
        self.submitted: list[dict] = []
        self._submit_result = submit_result

    def submit(self, payload: dict) -> bool:
        self.submitted.append(payload)
        return self._submit_result


def make_client(**overrides) -> EngineWSClient:
    defaults = dict(
        ws_url="ws://127.0.0.1:3100/api/v1/realtime/engine-ws",
        signer=InternalRequestSigner("test-secret"),
        apply_command=lambda command: (True, "ok"),
    )
    defaults.update(overrides)
    return EngineWSClient(**defaults)


class AuthenticateTest(unittest.TestCase):
    def test_sends_signed_auth_frame_using_ws_stand_in_method_and_path(self) -> None:
        secret = "test-secret"
        client = make_client(signer=InternalRequestSigner(secret))
        ws = FakeWebSocket(
            recv_queue=[json.dumps({"type": "auth", "id": "srv-1", "ts": 1.0, "payload": {"status": "ok"}})]
        )

        asyncio.run(client._authenticate(ws))

        self.assertEqual(len(ws.sent), 1)
        sent = json.loads(ws.sent[0])
        self.assertEqual(sent["type"], "auth")
        payload = sent["payload"]
        self.assertIn("signature", payload)
        self.assertIn("timestamp", payload)
        self.assertIn("nonce", payload)

        body_hash = hashlib.sha256(b"").hexdigest()
        signing_string = (
            f"{ENGINE_WS_AUTH_METHOD}\n{ENGINE_WS_AUTH_PATH}\n{body_hash}\n"
            f"{payload['timestamp']}\n{payload['nonce']}"
        )
        expected_signature = hmac.new(secret.encode(), signing_string.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(payload["signature"], expected_signature)

    def test_raises_when_backend_rejects_auth(self) -> None:
        client = make_client()
        ws = FakeWebSocket(
            recv_queue=[json.dumps({"type": "auth", "id": "srv-1", "ts": 1.0, "payload": {"status": "rejected"}})]
        )

        with self.assertRaises(EngineWSAuthError):
            asyncio.run(client._authenticate(ws))

    def test_raises_on_malformed_reply(self) -> None:
        client = make_client()
        ws = FakeWebSocket(recv_queue=["not json"])

        with self.assertRaises(Exception):
            asyncio.run(client._authenticate(ws))


class BackoffTest(unittest.TestCase):
    def test_delay_never_exceeds_cap(self) -> None:
        client = make_client(reconnect_base_seconds=1.0, reconnect_cap_seconds=60.0)
        for attempt in range(25):
            delay = client._next_backoff_delay(attempt)
            self.assertGreaterEqual(delay, 0.0)
            self.assertLessEqual(delay, 60.0)

    def test_first_attempt_is_bounded_by_base(self) -> None:
        client = make_client(reconnect_base_seconds=1.0, reconnect_cap_seconds=60.0)
        self.assertLessEqual(client._next_backoff_delay(0), 1.0)

    def test_delay_grows_with_attempt_before_capping(self) -> None:
        client = make_client(reconnect_base_seconds=1.0, reconnect_cap_seconds=60.0)
        # attempt=5 -> uncapped 32s, well under the 60s cap, so the upper
        # bound of the jitter range should have grown past attempt=0's.
        self.assertLessEqual(client._next_backoff_delay(5), 32.0)


class HandleCommandTest(unittest.TestCase):
    def test_applies_command_and_submits_ack(self) -> None:
        applied = []

        def apply_command(command):
            applied.append(command)
            return True, "blocked"

        client = make_client(apply_command=apply_command)
        client._ack_publisher = FakeAckPublisher()

        asyncio.run(
            client._handle_command({"command_id": "cmd-1", "action": "block", "ip_address": "203.0.113.10"})
        )

        self.assertEqual(len(applied), 1)
        self.assertEqual(len(client._ack_publisher.submitted), 1)
        ack = client._ack_publisher.submitted[0]
        self.assertEqual(ack["command_id"], "cmd-1")
        self.assertEqual(ack["status"], "blocked")
        self.assertEqual(ack["ack_source"], "engine_ws")

    def test_failed_apply_acks_with_error_prefixed_status(self) -> None:
        client = make_client(apply_command=lambda command: (False, "invalid_command"))
        client._ack_publisher = FakeAckPublisher()

        asyncio.run(client._handle_command({"command_id": "cmd-2", "action": "block", "ip_address": "1.2.3.4"}))

        ack = client._ack_publisher.submitted[0]
        self.assertEqual(ack["status"], "error:invalid_command")

    def test_missing_command_id_is_not_acked(self) -> None:
        client = make_client(apply_command=lambda command: (False, "invalid_command"))
        client._ack_publisher = FakeAckPublisher()

        asyncio.run(client._handle_command({"action": "block", "ip_address": "1.2.3.4"}))

        self.assertEqual(client._ack_publisher.submitted, [])

    def test_full_ack_queue_does_not_raise(self) -> None:
        client = make_client(apply_command=lambda command: (True, "blocked"))
        client._ack_publisher = FakeAckPublisher(submit_result=False)

        # Should log a warning internally and return without raising.
        asyncio.run(client._handle_command({"command_id": "cmd-3", "action": "block", "ip_address": "1.2.3.4"}))


class HandleIncomingTest(unittest.TestCase):
    def test_ping_triggers_pong_reply(self) -> None:
        client = make_client()
        ws = FakeWebSocket()
        client._ws = ws

        asyncio.run(client._handle_incoming(json.dumps({"type": "ping", "id": "1", "ts": 1.0, "payload": {}})))

        self.assertEqual(len(ws.sent), 1)
        sent = json.loads(ws.sent[0])
        self.assertEqual(sent["type"], "pong")

    def test_pong_is_ignored(self) -> None:
        client = make_client()
        ws = FakeWebSocket()
        client._ws = ws

        asyncio.run(client._handle_incoming(json.dumps({"type": "pong", "id": "1", "ts": 1.0, "payload": {}})))

        self.assertEqual(ws.sent, [])

    def test_unrecognized_type_is_ignored_without_raising(self) -> None:
        client = make_client()
        ws = FakeWebSocket()
        client._ws = ws

        asyncio.run(client._handle_incoming(json.dumps({"type": "telemetry", "id": "1", "ts": 1.0, "payload": {}})))

        self.assertEqual(ws.sent, [])

    def test_malformed_json_is_ignored_without_raising(self) -> None:
        client = make_client()
        asyncio.run(client._handle_incoming("not json"))

    def test_command_frame_dispatches_to_handle_command(self) -> None:
        applied = []
        client = make_client(apply_command=lambda command: applied.append(command) or (True, "blocked"))
        client._ack_publisher = FakeAckPublisher()

        asyncio.run(
            client._handle_incoming(
                json.dumps(
                    {
                        "type": "command",
                        "id": "1",
                        "ts": 1.0,
                        "payload": {"command_id": "cmd-4", "action": "block", "ip_address": "1.2.3.4"},
                    }
                )
            )
        )

        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0]["command_id"], "cmd-4")


class CatchupTest(unittest.TestCase):
    def test_no_poller_configured_is_a_no_op(self) -> None:
        client = make_client(catchup_poller=None)
        asyncio.run(client._run_catchup())  # should not raise

    def test_applies_and_acks_each_command_via_rest(self) -> None:
        applied = []

        def apply_command(command):
            applied.append(command)
            return True, "blocked"

        fake_poller = Mock()
        fake_poller.poll_commands.return_value = [
            {"command_id": "cmd-5", "action": "block", "ip_address": "1.2.3.4"},
            {"command_id": "cmd-6", "action": "unblock", "ip_address": "1.2.3.5"},
        ]

        client = make_client(
            apply_command=apply_command,
            catchup_poller=fake_poller,
            catchup_ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
        )

        asyncio.run(client._run_catchup())

        self.assertEqual(len(applied), 2)
        self.assertEqual(fake_poller.ack_command.call_count, 2)
        fake_poller.ack_command.assert_any_call(
            ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
            command_id="cmd-5",
            status="blocked",
        )

    def test_failed_apply_acks_with_error_prefixed_status(self) -> None:
        fake_poller = Mock()
        fake_poller.poll_commands.return_value = [{"command_id": "cmd-7", "action": "block", "ip_address": "1.2.3.4"}]

        client = make_client(
            apply_command=lambda command: (False, "invalid_command"),
            catchup_poller=fake_poller,
            catchup_ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
        )

        asyncio.run(client._run_catchup())

        fake_poller.ack_command.assert_called_once_with(
            ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
            command_id="cmd-7",
            status="error:invalid_command",
        )

    def test_no_ack_endpoint_skips_acking(self) -> None:
        fake_poller = Mock()
        fake_poller.poll_commands.return_value = [{"command_id": "cmd-8", "action": "block", "ip_address": "1.2.3.4"}]

        client = make_client(
            apply_command=lambda command: (True, "blocked"),
            catchup_poller=fake_poller,
            catchup_ack_endpoint_url=None,
        )

        asyncio.run(client._run_catchup())

        fake_poller.ack_command.assert_not_called()


class WSAuthConstantContractTest(unittest.TestCase):
    """Guardrail against silent cross-repo drift.

    ``ENGINE_WS_AUTH_METHOD``/``ENGINE_WS_AUTH_PATH`` are independently
    defined here and in
    ``backend/app/features/realtime/engine_ws_schemas.py`` — there's no
    shared source of truth across the two repos, so this pins the exact
    literal values. If you're editing this test because the assertion
    failed, you MUST make the matching edit in
    ``backend/app/features/realtime/engine_ws_schemas.py`` (and its own
    mirror of this test) or the engine will silently fail to authenticate
    against the backend.
    """

    def test_auth_constants_match_documented_contract(self) -> None:
        self.assertEqual(ENGINE_WS_AUTH_METHOD, "WS_AUTH")
        self.assertEqual(ENGINE_WS_AUTH_PATH, "/api/v1/realtime/engine-ws")


if __name__ == "__main__":
    unittest.main()
