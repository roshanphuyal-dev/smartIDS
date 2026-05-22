from typing import Any, Dict

import joblib
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier


class SklearnModel:
    def __init__(self, model_type: str = "random_forest"):
        self.model_type = model_type
        self.model = self._build_model(model_type)

    def _build_model(self, model_type: str):
        if model_type == "random_forest":
            return RandomForestClassifier(
                n_estimators=100,
                max_depth=None,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            )

        if model_type == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(
                learning_rate=0.1,
                max_iter=100,
                random_state=42,
            )

        raise ValueError(f"Unsupported sklearn model type: {model_type}")

    def train(self, X_train, y_train):
        self.model.fit(X_train, y_train)
        return self.model

    def predict(self, X):
        return self.model.predict(X)

    def predict_proba(self, X):
        if not hasattr(self.model, "predict_proba"):
            raise AttributeError(
                f"{self.model_type} does not support predict_proba"
            )

        return self.model.predict_proba(X)

    def save(self, output_path: str):
        joblib.dump(self.model, output_path)

    @staticmethod
    def load(model_path: str):
        return joblib.load(model_path)

    def get_params(self) -> Dict[str, Any]:
        return self.model.get_params()