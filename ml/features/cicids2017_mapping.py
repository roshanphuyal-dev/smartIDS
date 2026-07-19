CICIDS2017_TO_INTERNAL = {
    "Destination Port": "dst_port",
    "Protocol": "protocol",
    "Flow Duration": "flow_duration",
    "Total Fwd Packets": "total_fwd_packets",
    "Total Length of Fwd Packets": "total_fwd_bytes",
    "Flow Bytes/s": "flow_bytes_per_sec",
    "Flow Packets/s": "flow_packets_per_sec",
    "Flow IAT Min": "flow_iat_min",
    "Flow IAT Max": "flow_iat_max",
    "Flow IAT Mean": "flow_iat_mean",
    "Flow IAT Std": "flow_iat_std",
    "Fwd IAT Min": "fwd_iat_min",
    "Fwd IAT Max": "fwd_iat_max",
    "Fwd IAT Mean": "fwd_iat_mean",
    "Fwd IAT Std": "fwd_iat_std",
    "Fwd IAT Total": "fwd_iat_total",
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
    "SYN Flag Count": "syn_flag_count",
    "RST Flag Count": "rst_flag_count",
    "PSH Flag Count": "psh_flag_count",
    "ACK Flag Count": "ack_flag_count",
    "URG Flag Count": "urg_flag_count",
    "Fwd Header Length": "fwd_header_length",
    "Init_Win_bytes_forward": "init_win_bytes_forward",
    "act_data_pkt_fwd": "act_data_pkt_fwd",
    "min_seg_size_forward": "min_seg_size_forward",
}


def normalize_cicids2017_label(label: object) -> str:
    value = str(label).strip().lower()

    if value in {"benign", "normal", "normal traffic"}:
        return "Normal Traffic"

    if value.startswith("ddos") or "ddos" in value:
        return "DDoS"

    if value.startswith("dos") or "dos" in value:
        return "DoS"

    if "portscan" in value or "port scan" in value:
        return "Port Scanning"

    if "ftp-patator" in value or "ssh-patator" in value:
        return "Brute Force"

    if "web attack" in value:
        return "Web Attacks"

    if value == "bot" or value == "bots":
        return "Bots"

    return str(label).strip()
