import platform

from response_engine.firewall.base import FirewallAdapter
from response_engine.firewall.linux_adapter import LinuxFirewallAdapter
from response_engine.firewall.windows_adapter import WindowsFirewallAdapter


def create_firewall_adapter() -> FirewallAdapter | None:
    system_name = platform.system().lower()

    if system_name == "windows":
        return WindowsFirewallAdapter()

    if system_name == "linux":
        return LinuxFirewallAdapter()

    return None
