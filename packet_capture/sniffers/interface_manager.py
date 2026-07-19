from __future__ import annotations

from scapy.all import get_if_list

try:
    from scapy.arch.windows import get_windows_if_list  # type: ignore
except Exception:  # pragma: no cover
    get_windows_if_list = None


class InterfaceManager:
    _LOOPBACK_KEYWORDS = ("loopback", "pseudo-interface", "pseudo interface")
    _VIRTUAL_KEYWORDS = (
        "virtual",
        "vmware",
        "virtualbox",
        "hyper-v",
        "hyperv",
        "vbox",
        "npcap loopback",
        "tunnel",
        "tap",
        "miniport",
    )
    _PREFERRED_KEYWORDS = (
        "wi-fi",
        "wifi",
        "wireless",
        "ethernet",
        "lan",
    )

    @staticmethod
    def list_interfaces():
        return get_if_list()

    @staticmethod
    def get_default_interface():
        best_interface = InterfaceManager.get_best_active_interface()
        if best_interface:
            return best_interface

        interfaces = get_if_list()

        if not interfaces:
            raise Exception("No network interfaces found")

        return interfaces[0]

    @staticmethod
    def get_best_active_interface():
        windows_interfaces = InterfaceManager._get_windows_interfaces()
        if not windows_interfaces:
            interfaces = get_if_list()
            return interfaces[0] if interfaces else None

        scored_interfaces = []
        for item in windows_interfaces:
            score = InterfaceManager._score_windows_interface(item)
            if score is None:
                continue
            scored_interfaces.append((score, str(item.get("name", "")).strip()))

        if not scored_interfaces:
            interfaces = get_if_list()
            return interfaces[0] if interfaces else None

        scored_interfaces.sort(key=lambda entry: entry[0], reverse=True)
        return scored_interfaces[0][1] or None

    @staticmethod
    def resolve_interface(identifier: str):
        requested = identifier.strip()
        if not requested:
            return InterfaceManager.get_default_interface()

        if requested in get_if_list():
            return requested

        if get_windows_if_list is not None:
            try:
                for item in get_windows_if_list():
                    if requested.lower() in {
                        str(item.get("name", "")).lower(),
                        str(item.get("description", "")).lower(),
                        str(item.get("guid", "")).lower(),
                    }:
                        return str(item.get("name"))
                    if requested.lower() in str(item.get("name", "")).lower():
                        return str(item.get("name"))
                    if requested.lower() in str(item.get("description", "")).lower():
                        return str(item.get("name"))
                    if requested.lower() in str(item.get("guid", "")).lower():
                        return str(item.get("name"))
            except Exception:
                pass

        return requested

    @staticmethod
    def _get_windows_interfaces():
        if get_windows_if_list is None:
            return []

        try:
            return list(get_windows_if_list())
        except Exception:
            return []

    @staticmethod
    def _score_windows_interface(item: dict):
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        guid = str(item.get("guid", "")).strip()
        searchable = " ".join(value for value in (name, description, guid) if value).lower()

        if not name:
            return None

        if any(keyword in searchable for keyword in InterfaceManager._LOOPBACK_KEYWORDS):
            return None

        ipv4_address = InterfaceManager._extract_ipv4(item)
        if not ipv4_address:
            return None

        score = 100

        if InterfaceManager._looks_physical(searchable):
            score += 100
        if any(keyword in searchable for keyword in InterfaceManager._PREFERRED_KEYWORDS):
            score += 50
        if any(keyword in searchable for keyword in InterfaceManager._VIRTUAL_KEYWORDS):
            score -= 120

        metric = InterfaceManager._extract_metric(item)
        if metric is not None:
            score -= min(50, max(0, metric))

        if InterfaceManager._looks_wired(searchable):
            score += 15

        return score

    @staticmethod
    def _extract_ipv4(item: dict):
        for key in ("ipv4", "IPv4", "ip", "address"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (list, tuple)):
                for entry in value:
                    if isinstance(entry, str) and "." in entry and ":" not in entry:
                        return entry.strip()

        ips = item.get("ips")
        if isinstance(ips, (list, tuple)):
            for entry in ips:
                entry_text = str(entry).strip()
                if "." in entry_text and ":" not in entry_text:
                    return entry_text

        return None

    @staticmethod
    def _extract_metric(item: dict):
        for key in ("metric", "ipv4_metric", "IPv4Metric", "win_index", "index"):
            value = item.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    @staticmethod
    def _looks_physical(searchable: str):
        physical_keywords = ("wifi", "wi-fi", "ethernet", "lan", "wireless", "intel", "realtek", "qualcomm", "broadcom")
        return any(keyword in searchable for keyword in physical_keywords)

    @staticmethod
    def _looks_wired(searchable: str):
        wired_keywords = ("ethernet", "lan")
        return any(keyword in searchable for keyword in wired_keywords)
