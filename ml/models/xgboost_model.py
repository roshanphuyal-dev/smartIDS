from typing import Any, Dict

import joblib
from xgboost import XGBClassifier


class XGBoostModel:
    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
        )

    def train(self, X_train, y_train):
        self.model.fit(X_train, y_train)
        return self.model

    def predict(self, X):
        return self.model.predict(X)

    def predict_proba(self, X):
        return self.model.predict_proba(X)

    def save(self, output_path: str):
        joblib.dump(self.model, output_path)

    @staticmethod
    def load(model_path: str):
        return joblib.load(model_path)

    def get_params(self) -> Dict[str, Any]:
        return self.model.get_params()