import math
import os

from ml.features.schema import FEATURE_COLUMNS
from feature_engine.stats import (
    safe_iat_stats,
    safe_max,
    safe_mean,
    safe_min,
    safe_rate,
    safe_std,
    safe_variance,
    sanitize_feature_dict,
)
from packet_capture.utils.logger import IDSLogger, log_event

_DIVERGENCE_REL_TOL = 1e-6
_DIVERGENCE_ABS_TOL = 1e-6


class SessionFeatureExtractor:
    def __init__(self):
        # Logger is created lazily (only if validation is enabled and a
        # divergence is actually logged) so the common case never touches
        # IDSLogger/log file setup.
        self._logger = None
        # Compares the list-based packet-length stats below against the
        # incremental (Welford) accumulators maintained on TrafficSession and
        # logs a warning on divergence. Instrumentation only: the extractor
        # still returns the list-based values regardless of this flag. See
        # Workstream 7 of the engine improvement plan.
        self._validate_incremental_stats = os.getenv(
            "SMARTIDS_FEATURE_EXTRACTION_VALIDATE", ""
        ).strip().lower() in {"1", "true", "yes", "on"}

    def extract(self, session):
        flow_duration = session.duration()

        packet_lengths = session.packet_lengths
        fwd_packet_lengths = session.fwd_packet_lengths

        flow_iat = safe_iat_stats(session.packet_timestamps)
        fwd_iat = safe_iat_stats(session.fwd_packet_timestamps)

        feature_values = {
            "dst_port": 0 if session.dst_port is None else session.dst_port,
            "protocol": session.protocol,
            "flow_duration": flow_duration,
            "total_fwd_packets": session.fwd_packet_count,
            "total_fwd_bytes": session.fwd_total_bytes,
            "flow_bytes_per_sec": safe_rate(session.total_bytes, flow_duration),
            "flow_packets_per_sec": safe_rate(session.packet_count, flow_duration),
            "packet_len_min": safe_min(packet_lengths),
            "packet_len_max": safe_max(packet_lengths),
            "packet_len_mean": safe_mean(packet_lengths),
            "packet_len_std": safe_std(packet_lengths),
            "packet_len_variance": safe_variance(packet_lengths),
            "avg_packet_size": session.average_packet_size(),
            "fwd_packet_len_min": safe_min(fwd_packet_lengths),
            "fwd_packet_len_max": safe_max(fwd_packet_lengths),
            "fwd_packet_len_mean": safe_mean(fwd_packet_lengths),
            "fwd_packet_len_std": safe_std(fwd_packet_lengths),
            "flow_iat_min": flow_iat["min"],
            "flow_iat_max": flow_iat["max"],
            "flow_iat_mean": flow_iat["mean"],
            "flow_iat_std": flow_iat["std"],
            "fwd_iat_min": fwd_iat["min"],
            "fwd_iat_max": fwd_iat["max"],
            "fwd_iat_mean": fwd_iat["mean"],
            "fwd_iat_std": fwd_iat["std"],
            "fwd_iat_total": fwd_iat["total"],
            "fwd_packets_per_sec": safe_rate(session.fwd_packet_count, flow_duration),
            "fin_flag_count": session.flag_counts["fin"],
            "syn_flag_count": session.flag_counts["syn"],
            "rst_flag_count": session.flag_counts["rst"],
            "psh_flag_count": session.flag_counts["psh"],
            "ack_flag_count": session.flag_counts["ack"],
            "urg_flag_count": session.flag_counts["urg"],
            "fwd_header_length": session.fwd_header_length,
            "init_win_bytes_forward": 0
            if session.init_win_bytes_forward is None
            else session.init_win_bytes_forward,
            "act_data_pkt_fwd": session.act_data_pkt_fwd,
            "min_seg_size_forward": 0
            if session.min_seg_size_forward is None
            else session.min_seg_size_forward,
        }

        if self._validate_incremental_stats:
            self._validate_against_incremental_stats(session, feature_values)

        sanitized = sanitize_feature_dict(feature_values)

        return {column: sanitized.get(column, 0.0) for column in FEATURE_COLUMNS}

    def _validate_against_incremental_stats(self, session, feature_values) -> None:
        """Compares list-based packet-length stats against the incremental
        (Welford) accumulators on the session and logs a warning per
        diverging field. Read-only: never changes what ``extract`` returns.
        """

        incremental_values = {
            "packet_len_min": session.packet_length_stats.get_min(),
            "packet_len_max": session.packet_length_stats.get_max(),
            "packet_len_mean": session.packet_length_stats.get_mean(),
            "packet_len_std": session.packet_length_stats.std(),
            "packet_len_variance": session.packet_length_stats.variance(),
            "fwd_packet_len_min": session.fwd_packet_length_stats.get_min(),
            "fwd_packet_len_max": session.fwd_packet_length_stats.get_max(),
            "fwd_packet_len_mean": session.fwd_packet_length_stats.get_mean(),
            "fwd_packet_len_std": session.fwd_packet_length_stats.std(),
        }

        for field_name, incremental_value in incremental_values.items():
            list_based_value = float(feature_values[field_name])
            if math.isclose(
                list_based_value,
                incremental_value,
                rel_tol=_DIVERGENCE_REL_TOL,
                abs_tol=_DIVERGENCE_ABS_TOL,
            ):
                continue

            if self._logger is None:
                self._logger = IDSLogger.get_logger(
                    "feature_engine.session_feature_extractor"
                )

            log_event(
                self._logger,
                "warning",
                "incremental feature stats diverged from list-based recomputation",
                {
                    "event_type": "feature_extraction_incremental_divergence",
                    "field": field_name,
                    "list_based_value": list_based_value,
                    "incremental_value": incremental_value,
                    "delta": incremental_value - list_based_value,
                    "session_packet_count": session.packet_count,
                },
            )
