from pathlib import Path

from ml.runtime.model_stack import (
    RuntimeModelBundleConfig,
    RuntimeModelStack,
)


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

    def predict(self, features: dict) -> dict | None:
        if not self.enabled or self.model_stack is None:
            return None
        return self.model_stack.predict(features)
