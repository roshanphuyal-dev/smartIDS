import ipaddress
import time
from datetime import datetime, timezone

from response_engine.firewall.factory import create_firewall_adapter
from response_engine.block_records import BlockRecordStore
from packet_capture.utils.logger import IDSLogger, log_event


class AutoBlocker:
    def __init__(self):
        self.firewall = create_firewall_adapter()
        self.block_cooldown_seconds = 60
        self._last_block_time = {}
        self._blocked_until = {}
        self._block_counts = {}
        self.logger = IDSLogger.get_logger("response.auto_blocker")
        self.record_store = BlockRecordStore()

    def block_if_needed(self, ip_address: str) -> tuple[bool, str]:
        return self.temp_block(ip_address=ip_address, duration_seconds=300)

    def temp_block(self, ip_address: str, duration_seconds: int) -> tuple[bool, str]:
        if self.firewall is None:
            return False, "unsupported_platform"

        if not self._is_valid_routable_ip(ip_address):
            return False, "invalid_or_loopback_ip"

        self.expire_blocks()

        now = time.time()
        last_time = self._last_block_time.get(ip_address)
        if last_time is not None and (now - last_time) < self.block_cooldown_seconds:
            return False, "cooldown_active"

        if self.firewall.is_blocked(ip_address):
            self._last_block_time[ip_address] = now
            self._blocked_until[ip_address] = now + max(1, int(duration_seconds))
            self._record("already_blocked", ip_address, duration_seconds)
            return True, "already_blocked"

        ok, status = self.firewall.block_ip(ip_address)
        if ok:
            self._last_block_time[ip_address] = now
            self._blocked_until[ip_address] = now + max(1, int(duration_seconds))
            self._block_counts[ip_address] = self._block_counts.get(ip_address, 0) + 1
            self._record(status, ip_address, duration_seconds)
            log_event(
                self.logger,
                "info",
                "response block action",
                {
                    "event_type": "response_block",
                    "action": "block",
                    "ip": ip_address,
                    "duration_seconds": duration_seconds,
                    "status": status,
                    "times_blocked": self._block_counts[ip_address],
                },
            )
        else:
            log_event(
                self.logger,
                "warning",
                "response block failed",
                {
                    "event_type": "response_block_failed",
                    "action": "block",
                    "ip": ip_address,
                    "duration_seconds": duration_seconds,
                    "status": status,
                },
            )
        return ok, status

    def expire_blocks(self):
        if self.firewall is None:
            return

        now = time.time()
        expired = [ip for ip, until in self._blocked_until.items() if now >= until]
        for ip_address in expired:
            ok, status = self.firewall.unblock_ip(ip_address)
            self._record("unblocked" if ok else status, ip_address, 0)
            log_event(
                self.logger,
                "info",
                "response unblock action",
                {
                    "event_type": "response_unblock",
                    "action": "unblock",
                    "ip": ip_address,
                    "status": status,
                },
            )
            self._blocked_until.pop(ip_address, None)
            self._last_block_time.pop(ip_address, None)

    def _record(self, status: str, ip_address: str, duration_seconds: int):
        blocked_until = None
        if duration_seconds > 0:
            blocked_until = datetime.fromtimestamp(
                time.time() + duration_seconds,
                tz=timezone.utc,
            ).isoformat()

        self.record_store.append_event(
            {
                "ip": ip_address,
                "status": status,
                "duration_seconds": duration_seconds,
                "blocked_until": blocked_until,
                "times_blocked": self._block_counts.get(ip_address, 0),
                "current_status": "blocked" if duration_seconds > 0 else "unblocked",
            }
        )

    def _is_valid_routable_ip(self, ip_address: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(ip_address)
            if ip_obj.is_loopback:
                return False
            return True
        except ValueError:
            return False
