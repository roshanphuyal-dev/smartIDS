from __future__ import annotations

import unittest
from unittest.mock import patch

from response_engine.backend_command_poller import BackendCommandPoller


class BackendCommandPollerTest(unittest.TestCase):
    def test_poll_commands_returns_empty_list_on_socket_reset(self) -> None:
        poller = BackendCommandPoller(endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands")

        with patch("response_engine.backend_command_poller.request.urlopen", side_effect=ConnectionResetError()):
            self.assertEqual(poller.poll_commands(), [])

    def test_ack_command_returns_false_on_socket_reset(self) -> None:
        poller = BackendCommandPoller(endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands")

        with patch("response_engine.backend_command_poller.request.urlopen", side_effect=ConnectionResetError()):
            self.assertFalse(
                poller.ack_command(
                    ack_endpoint_url="http://127.0.0.1:3100/api/v1/engine-commands/ack",
                    command_id="cmd-1",
                    status="blocked",
                )
            )


if __name__ == "__main__":
    unittest.main()
