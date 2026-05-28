import subprocess

from response_engine.firewall.base import FirewallAdapter


class WindowsFirewallAdapter(FirewallAdapter):
    RULE_PREFIX = "SmartIDS_Block_"

    def block_ip(self, ip_address: str) -> tuple[bool, str]:
        rule_name = self._rule_name(ip_address)

        if self.is_blocked(ip_address):
            return True, "already_blocked"

        cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "add",
            "rule",
            f"name={rule_name}",
            "dir=in",
            "action=block",
            f"remoteip={ip_address}",
            "enable=yes",
        ]

        if self._run(cmd):
            return True, "blocked"

        return False, "block_failed"

    def unblock_ip(self, ip_address: str) -> tuple[bool, str]:
        rule_name = self._rule_name(ip_address)
        cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "delete",
            "rule",
            f"name={rule_name}",
        ]

        if self._run(cmd):
            return True, "unblocked"

        return False, "unblock_failed"

    def is_blocked(self, ip_address: str) -> bool:
        rule_name = self._rule_name(ip_address)
        cmd = [
            "netsh",
            "advfirewall",
            "firewall",
            "show",
            "rule",
            f"name={rule_name}",
        ]

        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            return result.returncode == 0 and rule_name in (result.stdout or "")
        except Exception:
            return False

    def _rule_name(self, ip_address: str) -> str:
        return f"{self.RULE_PREFIX}{ip_address}"

    def _run(self, command: list[str]) -> bool:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False
