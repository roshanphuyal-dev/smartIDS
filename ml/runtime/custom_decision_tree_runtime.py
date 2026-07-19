from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import sys
from typing import Iterator

import numpy as np


@dataclass
class TreeNode:
    is_leaf: bool = False
    prediction: int = 0
    class_counts: list[int] | None = None
    feature_index: int | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None


class CustomDecisionTreeClassifier:
    def predict(self, frame):
        rows = self._coerce_rows(frame)
        return np.asarray([self._predict_row(row) for row in rows], dtype=int)

    def predict_proba(self, frame):
        rows = self._coerce_rows(frame)
        probabilities = [self._predict_row_proba(row) for row in rows]
        return np.asarray(probabilities, dtype=float)

    @staticmethod
    def _coerce_rows(frame) -> np.ndarray:
        if hasattr(frame, "to_numpy"):
            return np.asarray(frame.to_numpy(dtype=float), dtype=float)
        return np.asarray(frame, dtype=float)

    def _predict_row(self, row: np.ndarray) -> int:
        node = self._descend(row)
        return int(getattr(node, "prediction", 0) or 0)

    def _predict_row_proba(self, row: np.ndarray) -> np.ndarray:
        node = self._descend(row)
        class_counts = getattr(node, "class_counts", None)
        if isinstance(class_counts, list) and class_counts:
            counts = np.asarray(class_counts, dtype=float)
            total = float(np.sum(counts))
            if total > 0:
                return counts / total

        n_classes = max(int(getattr(self, "n_classes", 1) or 1), 1)
        probabilities = np.zeros(n_classes, dtype=float)
        prediction = int(getattr(node, "prediction", 0) or 0)
        if 0 <= prediction < n_classes:
            probabilities[prediction] = 1.0
        return probabilities

    def _descend(self, row: np.ndarray) -> TreeNode:
        node = getattr(self, "root", None)
        while node is not None and not bool(getattr(node, "is_leaf", False)):
            feature_index = int(getattr(node, "feature_index", 0) or 0)
            threshold = float(getattr(node, "threshold", 0.0) or 0.0)
            value = float(row[feature_index]) if feature_index < len(row) else 0.0
            node = getattr(node, "left", None) if value <= threshold else getattr(node, "right", None)

        return node if node is not None else TreeNode(is_leaf=True, prediction=0, class_counts=[1])


@contextmanager
def install_runtime_aliases() -> Iterator[None]:
    main_module = sys.modules.get("__main__")
    if main_module is None:
        yield
        return

    original_classifier = getattr(main_module, "CustomDecisionTreeClassifier", None)
    original_tree_node = getattr(main_module, "TreeNode", None)
    had_classifier = hasattr(main_module, "CustomDecisionTreeClassifier")
    had_tree_node = hasattr(main_module, "TreeNode")

    setattr(main_module, "CustomDecisionTreeClassifier", CustomDecisionTreeClassifier)
    setattr(main_module, "TreeNode", TreeNode)
    try:
        yield
    finally:
        if had_classifier:
            setattr(main_module, "CustomDecisionTreeClassifier", original_classifier)
        else:
            delattr(main_module, "CustomDecisionTreeClassifier")

        if had_tree_node:
            setattr(main_module, "TreeNode", original_tree_node)
        else:
            delattr(main_module, "TreeNode")
