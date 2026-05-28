CICIDS2017_TO_INTERNAL = {
    "Destination Port": "dst_port",
    "Flow Duration": "flow_duration",
    "Total Fwd Packets": "total_fwd_packets",
    "Total Length of Fwd Packets": "total_fwd_bytes",
    "Flow Bytes/s": "flow_bytes_per_sec",
    "Flow Packets/s": "flow_packets_per_sec",
    "Fwd Packet Length Max": "fwd_packet_len_max",
    "Fwd Packet Length Min": "fwd_packet_len_min",
    "Fwd Packet Length Mean": "fwd_packet_len_mean",
    "Fwd Packet Length Std": "fwd_packet_len_std",
    "Min Packet Length": "packet_len_min",
    "Max Packet Length": "packet_len_max",
    "Packet Length Mean": "packet_len_mean",
    "Packet Length Std": "packet_len_std",
    "Packet Length Variance": "packet_len_variance",
    "Average Packet Size": "avg_packet_size",
    "Fwd Packets/s": "fwd_packets_per_sec",
    "FIN Flag Count": "fin_flag_count",
    "PSH Flag Count": "psh_flag_count",
    "ACK Flag Count": "ack_flag_count",
    "Init_Win_bytes_forward": "init_win_bytes_forward",
    "act_data_pkt_fwd": "act_data_pkt_fwd",
    "min_seg_size_forward": "min_seg_size_forward",
}


def normalize_cicids2017_label(label: object) -> str:
    value = str(label).strip().lower()

    if value in {"benign", "normal", "normal traffic"}:
        return "Normal Traffic"

    if value.startswith("dos") or "dos" in value:
        return "DoS"

    if value.startswith("ddos") or "ddos" in value:
        return "DDoS"

    if "portscan" in value or "port scan" in value:
        return "Port Scanning"

    if "ftp-patator" in value or "ssh-patator" in value:
        return "Brute Force"

    if "web attack" in value:
        return "Web Attacks"

    if value == "bot" or value == "bots":
        return "Bots"

    return str(label).strip()
