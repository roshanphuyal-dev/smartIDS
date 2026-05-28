from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.features.schema import FEATURE_COLUMNS


class LivePredictor:
    def __init__(self):
        self.model_path = Path("ml/saved_models/cicids2017_live_compatible_model.pkl")
        self.encoder_path = Path("ml/saved_models/live_compatible_label_encoder.pkl")
        self.feature_columns_path = Path("ml/saved_models/live_compatible_feature_columns.json")

        self.enabled = False
        self.model = None
        self.label_encoder = None

        self._load_artifacts()

    def _load_artifacts(self):
        if not self.model_path.exists() or not self.encoder_path.exists():
            return

        self.model = joblib.load(self.model_path)
        self.label_encoder = joblib.load(self.encoder_path)
        self.enabled = True

    def predict(self, features: dict) -> dict | None:
        if not self.enabled:
            return None

        row = {column: float(features.get(column, 0.0)) for column in FEATURE_COLUMNS}
        frame = pd.DataFrame([row], columns=FEATURE_COLUMNS)
        frame = frame.replace([np.inf, -np.inf], 0).fillna(0)

        prediction_encoded = int(self.model.predict(frame)[0])
        prediction_label = str(self.label_encoder.inverse_transform([prediction_encoded])[0])

        confidence = 0.0
        if hasattr(self.model, "predict_proba"):
            probabilities = self.model.predict_proba(frame)[0]
            confidence = float(np.max(probabilities))

        return {
            "label": prediction_label,
            "confidence": confidence,
            "encoded": prediction_encoded,
        }
