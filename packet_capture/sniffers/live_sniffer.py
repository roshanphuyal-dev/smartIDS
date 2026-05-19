from scapy.all import * # type: ignore

def start_sniffing():
    print("Sniffing started...")
    print()
    print()
    packet = sniff(count=1) # type: ignore
    print("Packet captured:")
    print()
    print()
    packet[0].show()