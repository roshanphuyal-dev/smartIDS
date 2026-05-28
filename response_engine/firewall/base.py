from abc import ABC, abstractmethod


class FirewallAdapter(ABC):
    @abstractmethod
    def block_ip(self, ip_address: str) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def unblock_ip(self, ip_address: str) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def is_blocked(self, ip_address: str) -> bool:
        raise NotImplementedError
