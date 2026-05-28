import argparse
import random
import time

from scapy.all import IP, TCP, UDP, Raw, send  # type: ignore


def _send_tcp_packet(dst_ip: str, dst_port: int, flags: str, payload_size: int):
    src_port = random.randint(1024, 65535)
    payload = b"A" * max(0, payload_size)
    packet = IP(dst=dst_ip) / TCP(sport=src_port, dport=dst_port, flags=flags) / Raw(load=payload)
    send(packet, verbose=False)


def _send_udp_packet(dst_ip: str, dst_port: int, payload_size: int):
    src_port = random.randint(1024, 65535)
    payload = b"B" * max(0, payload_size)
    packet = IP(dst=dst_ip) / UDP(sport=src_port, dport=dst_port) / Raw(load=payload)
    send(packet, verbose=False)


def replay_normal(dst_ip: str, delay_seconds: float):
    for _ in range(15):
        _send_tcp_packet(dst_ip=dst_ip, dst_port=443, flags="PA", payload_size=120)
        time.sleep(delay_seconds)


def replay_port_sweep(dst_ip: str, delay_seconds: float):
    for port in range(1, 120):
        _send_tcp_packet(dst_ip=dst_ip, dst_port=port, flags="S", payload_size=0)
        time.sleep(delay_seconds)


def replay_bruteforce_like(dst_ip: str, delay_seconds: float, service_port: int):
    for _ in range(40):
        _send_tcp_packet(dst_ip=dst_ip, dst_port=service_port, flags="PA", payload_size=80)
        time.sleep(delay_seconds)


def replay_mixed(dst_ip: str, delay_seconds: float):
    replay_normal(dst_ip, delay_seconds)
    replay_port_sweep(dst_ip, delay_seconds / 2.0)
    replay_bruteforce_like(dst_ip, delay_seconds / 2.0, service_port=22)
    for _ in range(10):
        _send_udp_packet(dst_ip=dst_ip, dst_port=53, payload_size=48)
        time.sleep(delay_seconds)


def main():
    parser = argparse.ArgumentParser(description="SmartIDS deterministic demo traffic replay")
    parser.add_argument("--target-ip", required=True, help="Destination IP on your lab network")
    parser.add_argument(
        "--mode",
        choices=["normal", "port_sweep", "bruteforce", "mixed"],
        default="mixed",
        help="Replay scenario",
    )
    parser.add_argument("--delay", type=float, default=0.02, help="Delay between packets (seconds)")
    parser.add_argument("--loops", type=int, default=1, help="How many times to run scenario")
    parser.add_argument("--service-port", type=int, default=22, help="Service port for bruteforce mode")

    args = parser.parse_args()

    print(f"Starting demo replay: mode={args.mode}, target={args.target_ip}, loops={args.loops}")

    for index in range(args.loops):
        print(f"Loop {index + 1}/{args.loops}")

        if args.mode == "normal":
            replay_normal(dst_ip=args.target_ip, delay_seconds=args.delay)
        elif args.mode == "port_sweep":
            replay_port_sweep(dst_ip=args.target_ip, delay_seconds=args.delay)
        elif args.mode == "bruteforce":
            replay_bruteforce_like(
                dst_ip=args.target_ip,
                delay_seconds=args.delay,
                service_port=args.service_port,
            )
        else:
            replay_mixed(dst_ip=args.target_ip, delay_seconds=args.delay)

    print("Demo replay complete.")


if __name__ == "__main__":
    main()
