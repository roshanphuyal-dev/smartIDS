import subprocess

from response_engine.firewall.base import FirewallAdapter


class LinuxFirewallAdapter(FirewallAdapter):
    def block_ip(self, ip_address: str) -> tuple[bool, str]:
        exists_cmd = ["iptables", "-C", "INPUT", "-s", ip_address, "-j", "DROP"]
        add_cmd = ["iptables", "-A", "INPUT", "-s", ip_address, "-j", "DROP"]

        if self._run(exists_cmd):
            return True, "already_blocked"

        if self._run(add_cmd):
            return True, "blocked"

        return False, "block_failed"

    def unblock_ip(self, ip_address: str) -> tuple[bool, str]:
        cmd = ["iptables", "-D", "INPUT", "-s", ip_address, "-j", "DROP"]
        if self._run(cmd):
            return True, "unblocked"
        return False, "unblock_failed"

    def is_blocked(self, ip_address: str) -> bool:
        cmd = ["iptables", "-C", "INPUT", "-s", ip_address, "-j", "DROP"]
        return self._run(cmd)

    def _run(self, command: list[str]) -> bool:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False
