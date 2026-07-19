import unittest

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN


class FeatureSchemaTest(unittest.TestCase):
    def test_feature_schema_is_canonical_and_unique(self) -> None:
        expected = [
            "dst_port",
            "protocol",
            "flow_duration",
            "total_fwd_packets",
            "total_fwd_bytes",
            "flow_bytes_per_sec",
            "flow_packets_per_sec",
            "packet_len_min",
            "packet_len_max",
            "packet_len_mean",
            "packet_len_std",
            "packet_len_variance",
            "avg_packet_size",
            "fwd_packet_len_min",
            "fwd_packet_len_max",
            "fwd_packet_len_mean",
            "fwd_packet_len_std",
            "flow_iat_min",
            "flow_iat_max",
            "flow_iat_mean",
            "flow_iat_std",
            "fwd_iat_min",
            "fwd_iat_max",
            "fwd_iat_mean",
            "fwd_iat_std",
            "fwd_iat_total",
            "fwd_packets_per_sec",
            "fin_flag_count",
            "syn_flag_count",
            "rst_flag_count",
            "psh_flag_count",
            "ack_flag_count",
            "urg_flag_count",
            "fwd_header_length",
            "init_win_bytes_forward",
            "act_data_pkt_fwd",
            "min_seg_size_forward",
        ]

        self.assertEqual(FEATURE_COLUMNS, expected)
        self.assertEqual(LABEL_COLUMN, "Attack Type")
        self.assertNotIn("src_port", FEATURE_COLUMNS)
        self.assertEqual(len(FEATURE_COLUMNS), len(set(FEATURE_COLUMNS)))
