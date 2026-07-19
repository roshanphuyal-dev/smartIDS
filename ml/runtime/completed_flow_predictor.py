import os
from pathlib import Path
from typing import Callable

from ml.runtime.model_stack import (
    RuntimeModelBundleConfig,
    RuntimeModelStack,
)
from packet_capture.forwarding.background_publisher import BackgroundPublisher


class CompletedFlowPredictor:
    def __init__(
        self,
        *,
        primary_bundle_dir: Path | str = Path("ml/saved_models/CICIDS_XGBOOSTER"),
        primary_model_filename: str = "cicids2018_xgboost_model.pkl",
        primary_encoder_filename: str = "cicids2018_xgboost_label_encoder.pkl",
        primary_feature_columns_filename: str = "cicids2018_xgboost_feature_columns.json",
        primary_metadata_filename: str | None = "cicids2018_xgboost_training_metadata.json",
        secondary_bundle_dir: Path | str = Path("ml/saved_models/CICIDS_DecisionTree"),
        secondary_model_filename: str = "custom_decision_tree_model.pkl",
        secondary_encoder_filename: str = "custom_decision_tree_label_encoder.pkl",
        secondary_feature_columns_filename: str = "custom_decision_tree_feature_columns.json",
        secondary_metadata_filename: str | None = "custom_decision_tree_metadata.json",
        publish_secondary_result: Callable[[dict, dict], None] | None = None,
    ):
        self.primary_bundle_dir = Path(primary_bundle_dir)
        self.secondary_bundle_dir = Path(secondary_bundle_dir)
        self.model_path = self.primary_bundle_dir / primary_model_filename
        self.encoder_path = self.primary_bundle_dir / primary_encoder_filename
        self.feature_columns_path = self.primary_bundle_dir / primary_feature_columns_filename
        self.secondary_model_path = self.secondary_bundle_dir / secondary_model_filename
        self.secondary_encoder_path = self.secondary_bundle_dir / secondary_encoder_filename
        self.secondary_feature_columns_path = self.secondary_bundle_dir / secondary_feature_columns_filename

        self.enabled = False
        self.model = None
        self.label_encoder = None
        self.artifact_error = None
        self.secondary_artifact_error = None
        self.model_stack = None
        self._publish_secondary_result = publish_secondary_result
        self._secondary_publisher: BackgroundPublisher | None = None

        self._primary_config = RuntimeModelBundleConfig(
            model_key="xgboost",
            model_name="XGBoost",
            bundle_dir=self.primary_bundle_dir,
            model_filename=primary_model_filename,
            encoder_filename=primary_encoder_filename,
            feature_columns_filename=primary_feature_columns_filename,
            metadata_filename=primary_metadata_filename,
        )
        self._secondary_config = RuntimeModelBundleConfig(
            model_key="decision_tree",
            model_name="DecisionTree",
            bundle_dir=self.secondary_bundle_dir,
            model_filename=secondary_model_filename,
            encoder_filename=secondary_encoder_filename,
            feature_columns_filename=secondary_feature_columns_filename,
            metadata_filename=secondary_metadata_filename,
        )

        self._load_artifacts()

    @staticmethod
    def _positive_int(value: int | None, *, env_name: str, default: int) -> int:
        if value is None:
            value = os.getenv(env_name, str(default))
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(1, parsed)

    def _load_artifacts(self):
        self.model_stack = RuntimeModelStack(
            primary_config=self._primary_config,
            secondary_config=self._secondary_config,
        )
        self.enabled = self.model_stack.enabled
        self.artifact_error = self.model_stack.artifact_error
        self.secondary_artifact_error = self.model_stack.secondary_artifact_error
        self.model = self.model_stack.primary_bundle.model if self.enabled else None
        self.label_encoder = self.model_stack.primary_bundle.label_encoder if self.enabled else None

        secondary_bundle = self.model_stack.secondary_bundle
        if secondary_bundle is not None and secondary_bundle.enabled and self._secondary_publisher is None:
            worker_count = self._positive_int(None, env_name="SMARTIDS_SECONDARY_MODEL_WORKERS", default=3)
            queue_size = self._positive_int(None, env_name="SMARTIDS_SECONDARY_MODEL_QUEUE_SIZE", default=256)
            self._secondary_publisher = BackgroundPublisher(
                name="completed-flow-secondary-model",
                publish=self._run_secondary_prediction,
                max_queue_size=queue_size,
                worker_count=worker_count,
            )

    @property
    def secondary_publisher(self) -> BackgroundPublisher | None:
        return self._secondary_publisher

    def predict(self, features: dict) -> dict | None:
        if not self.enabled or self.model_stack is None:
            return None
        return self.model_stack.predict(features)

    def predict_primary(self, features: dict) -> dict | None:
        if not self.enabled or self.model_stack is None:
            return None
        return self.model_stack.predict_primary(features)

    def predict_primary_and_submit_secondary(self, features: dict, context: dict) -> dict | None:
        """Builds the feature frame once and reuses it for both the
        synchronous primary prediction and the async secondary dispatch,
        instead of each building its own frame from the same features dict.
        """
        if not self.enabled or self.model_stack is None:
            return None
        frame = self.model_stack.build_frame(features)
        prediction = self.model_stack.predict_primary_from_frame(frame)
        self._submit_secondary_frame(frame, context)
        return prediction

    def submit_secondary(self, features: dict, context: dict) -> bool:
        if self.model_stack is None:
            return False
        frame = self.model_stack.build_frame(features)
        return self._submit_secondary_frame(frame, context)

    def _submit_secondary_frame(self, frame, context: dict) -> bool:
        if self.model_stack is None:
            return False
        secondary_bundle = self.model_stack.secondary_bundle
        if secondary_bundle is None or not secondary_bundle.enabled:
            return False
        if self._secondary_publisher is None:
            return False

        return self._secondary_publisher.submit({"frame": frame, "context": context})

    def _run_secondary_prediction(self, payload: dict) -> bool:
        frame = payload["frame"]
        context = payload["context"]
        result = self.model_stack.secondary_bundle.predict(frame)
        if self._publish_secondary_result is not None:
            self._publish_secondary_result(result, context)
        return True
