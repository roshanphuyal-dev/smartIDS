from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_COLUMNS
from ml.runtime.artifact_validation import RuntimeArtifactError, load_runtime_model_artifacts


@dataclass(frozen=True)
class RuntimeModelBundleConfig:
    model_key: str
    model_name: str
    bundle_dir: Path
    model_filename: str
    encoder_filename: str
    feature_columns_filename: str
    metadata_filename: str | None = None


class RuntimeModelBundle:
    def __init__(self, config: RuntimeModelBundleConfig) -> None:
        self.config = config
        self.model_path = config.bundle_dir / config.model_filename
        self.encoder_path = config.bundle_dir / config.encoder_filename
        self.feature_columns_path = config.bundle_dir / config.feature_columns_filename
        self.metadata_path = None if config.metadata_filename is None else config.bundle_dir / config.metadata_filename

        self.enabled = False
        self.model = None
        self.label_encoder = None
        self.metadata: dict[str, Any] = {}
        self.artifact_error: str | None = None

        self._load_artifacts()

    def _load_artifacts(self) -> None:
        try:
            self.model, self.label_encoder = load_runtime_model_artifacts(
                self.model_path,
                self.encoder_path,
                self.feature_columns_path,
            )
            self.metadata = self._load_metadata()
        except RuntimeArtifactError as error:
            self.artifact_error = str(error)
            return

        self.enabled = True
        self.artifact_error = None

    def _load_metadata(self) -> dict[str, Any]:
        if self.metadata_path is None or not self.metadata_path.exists():
            return {}

        try:
            loaded = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}

        return loaded if isinstance(loaded, dict) else {}

    def predict(self, frame: pd.DataFrame) -> dict[str, Any]:
        encoded = int(self.model.predict(frame)[0])
        label = str(self.label_encoder.inverse_transform([encoded])[0])

        confidence = 0.0
        probabilities: list[float] | None = None
        if hasattr(self.model, "predict_proba"):
            raw_probabilities = self.model.predict_proba(frame)[0]
            probabilities = [float(value) for value in raw_probabilities]
            confidence = float(np.max(raw_probabilities))

        return {
            "model_key": self.config.model_key,
            "model_name": self.config.model_name,
            "bundle_dir": str(self.config.bundle_dir),
            "model_path": str(self.model_path),
            "encoder_path": str(self.encoder_path),
            "feature_columns_path": str(self.feature_columns_path),
            "metadata_path": None if self.metadata_path is None else str(self.metadata_path),
            "metadata": dict(self.metadata),
            "label": label,
            "confidence": confidence,
            "encoded": encoded,
            "probabilities": probabilities,
        }


class RuntimeModelStack:
    def __init__(
        self,
        *,
        primary_config: RuntimeModelBundleConfig,
        secondary_config: RuntimeModelBundleConfig | None = None,
    ) -> None:
        self.primary_bundle = RuntimeModelBundle(primary_config)
        self.secondary_bundle = None if secondary_config is None else RuntimeModelBundle(secondary_config)

        self.enabled = self.primary_bundle.enabled
        self.artifact_error = self.primary_bundle.artifact_error
        self.secondary_artifact_error = None if self.secondary_bundle is None else self.secondary_bundle.artifact_error

    def predict(self, features: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        row = {column: float(features.get(column, 0.0)) for column in FEATURE_COLUMNS}
        frame = pd.DataFrame([row], columns=FEATURE_COLUMNS)
        frame = frame.replace([np.inf, -np.inf], 0).fillna(0)

        primary_prediction = self.primary_bundle.predict(frame)
        model_outputs = {"primary": primary_prediction}
        secondary_enabled = False
        if self.secondary_bundle is not None and self.secondary_bundle.enabled:
            model_outputs["secondary"] = self.secondary_bundle.predict(frame)
            secondary_enabled = True

        return {
            "label": primary_prediction["label"],
            "confidence": primary_prediction["confidence"],
            "encoded": primary_prediction["encoded"],
            "model_key": primary_prediction["model_key"],
            "model_name": primary_prediction["model_name"],
            "model_outputs": model_outputs,
            "model_stack": {
                "primary_enabled": self.primary_bundle.enabled,
                "secondary_enabled": secondary_enabled,
                "primary_artifact_error": self.primary_bundle.artifact_error,
                "secondary_artifact_error": self.secondary_artifact_error,
            },
        }
