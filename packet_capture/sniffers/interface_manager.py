from scapy.all import get_if_list


class InterfaceManager:
    @staticmethod
    def list_interfaces():
        return get_if_list()

    @staticmethod
    def get_default_interface():
        interfaces = get_if_list()

        if not interfaces:
            raise Exception("No network interfaces found")

        return interfaces[0]
