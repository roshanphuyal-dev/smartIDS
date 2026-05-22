import json
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


class MetricsEvaluator:
    def __init__(self):
        pass

    def evaluate(
        self,
        y_true,
        y_pred,
        labels: Optional[Sequence[int]] = None,
        target_names: Optional[Sequence[str]] = None,
    ) -> Dict:
        metrics = {
            "accuracy": float(
                accuracy_score(y_true, y_pred)
            ),
            "precision": float(
                precision_score(
                    y_true,
                    y_pred,
                    average="weighted",
                    zero_division=0,
                )
            ),
            "recall": float(
                recall_score(
                    y_true,
                    y_pred,
                    average="weighted",
                    zero_division=0,
                )
            ),
            "f1_score": float(
                f1_score(
                    y_true,
                    y_pred,
                    average="weighted",
                    zero_division=0,
                )
            ),
            "confusion_matrix": confusion_matrix(
                y_true,
                y_pred,
                labels=labels,
            ).tolist(),
            "classification_report": classification_report(
                y_true,
                y_pred,
                labels=labels,
                target_names=target_names,
                output_dict=True,
                zero_division=0,
            ),
        }

        return metrics

    def print_summary(self, metrics: Dict):
        print("\n========== MODEL PERFORMANCE ==========")

        print(f"Accuracy  : {metrics['accuracy']:.4f}")
        print(f"Precision : {metrics['precision']:.4f}")
        print(f"Recall    : {metrics['recall']:.4f}")
        print(f"F1 Score  : {metrics['f1_score']:.4f}")

        print("\nConfusion Matrix:")
        print(np.array(metrics["confusion_matrix"]))

    def save_report(
        self,
        metrics: Dict,
        output_path: str,
    ):
        output_file = Path(output_path)

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(metrics, file, indent=4)
