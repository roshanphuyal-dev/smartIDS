from __future__ import annotations

import unittest
from unittest.mock import patch

from packet_capture.forwarding.fastapi_alert_forwarder import FastAPIAlertForwarder


class AlertForwarderTest(unittest.TestCase):
    def test_publish_alert_returns_false_on_socket_reset(self) -> None:
        forwarder = FastAPIAlertForwarder(
            endpoint_url="http://127.0.0.1:3100/api/v1/alerts/upsert",
        )

        with patch(
            "packet_capture.forwarding.fastapi_alert_forwarder.request.urlopen",
            side_effect=ConnectionResetError(),
        ):
            self.assertFalse(forwarder.publish_alert({"attack_type": "Brute Force"}))


if __name__ == "__main__":
    unittest.main()
