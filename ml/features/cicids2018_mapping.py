from __future__ import annotations


CICIDS2018_TO_INTERNAL = {
    "Dst Port": "dst_port",
    "Protocol": "protocol",
    "Flow Duration": "flow_duration",
    "Tot Fwd Pkts": "total_fwd_packets",
    "TotLen Fwd Pkts": "total_fwd_bytes",
    "Flow Byts/s": "flow_bytes_per_sec",
    "Flow Pkts/s": "flow_packets_per_sec",
    "Pkt Len Min": "packet_len_min",
    "Pkt Len Max": "packet_len_max",
    "Pkt Len Mean": "packet_len_mean",
    "Pkt Len Std": "packet_len_std",
    "Pkt Len Var": "packet_len_variance",
    "Pkt Size Avg": "avg_packet_size",
    "Fwd Pkt Len Min": "fwd_packet_len_min",
    "Fwd Pkt Len Max": "fwd_packet_len_max",
    "Fwd Pkt Len Mean": "fwd_packet_len_mean",
    "Fwd Pkt Len Std": "fwd_packet_len_std",
    "Flow IAT Min": "flow_iat_min",
    "Flow IAT Max": "flow_iat_max",
    "Flow IAT Mean": "flow_iat_mean",
    "Flow IAT Std": "flow_iat_std",
    "Fwd IAT Min": "fwd_iat_min",
    "Fwd IAT Max": "fwd_iat_max",
    "Fwd IAT Mean": "fwd_iat_mean",
    "Fwd IAT Std": "fwd_iat_std",
    "Fwd IAT Tot": "fwd_iat_total",
    "Fwd Pkts/s": "fwd_packets_per_sec",
    "FIN Flag Cnt": "fin_flag_count",
    "SYN Flag Cnt": "syn_flag_count",
    "RST Flag Cnt": "rst_flag_count",
    "PSH Flag Cnt": "psh_flag_count",
    "ACK Flag Cnt": "ack_flag_count",
    "URG Flag Cnt": "urg_flag_count",
    "Fwd Header Len": "fwd_header_length",
    "Init Fwd Win Byts": "init_win_bytes_forward",
    "Fwd Act Data Pkts": "act_data_pkt_fwd",
    "Fwd Seg Size Min": "min_seg_size_forward",
}


def normalize_cicids2018_label(label: object) -> str:
    value = str(label).strip().lower()

    if value in {"benign", "normal", "normal traffic"}:
        return "Normal Traffic"

    if value.startswith("ddos") or "ddos" in value or "hoic" in value or "loic" in value:
        return "DDoS"

    if value.startswith("dos") or " dos" in value or "hulk" in value or "goldeneye" in value or "slowhttptest" in value or "slowloris" in value:
        return "DoS"

    if "bruteforce" in value or "brute force" in value:
        return "Brute Force"

    if value == "bot" or value == "bots":
        return "Bots"

    if "web attack" in value or "sql injection" in value or value == "xss":
        return "Web Attacks"

    if "infilteration" in value or "infiltration" in value:
        return "Infiltration"

    if "heartbleed" in value:
        return "Heartbleed"

    return str(label).strip()
