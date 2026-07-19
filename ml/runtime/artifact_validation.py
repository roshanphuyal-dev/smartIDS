from __future__ import annotations

import json
from pathlib import Path

import joblib

from ml.features.schema import FEATURE_COLUMNS
from ml.runtime.custom_decision_tree_runtime import install_runtime_aliases


class RuntimeArtifactError(ValueError):
    pass


def _checksum_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def load_runtime_model_artifacts(
    model_path: Path,
    encoder_path: Path,
    feature_columns_path: Path,
):
    missing_paths = [
        str(path)
        for path in (model_path, encoder_path, feature_columns_path)
        if not path.exists()
    ]
    if missing_paths:
        raise RuntimeArtifactError(
            "Missing runtime artifacts: " + ", ".join(missing_paths)
        )

    with feature_columns_path.open("r", encoding="utf-8") as file:
        saved_feature_columns = json.load(file)

    if saved_feature_columns != FEATURE_COLUMNS:
        raise RuntimeArtifactError(
            "Saved feature schema does not match canonical FEATURE_COLUMNS"
        )

    # Verify integrity before deserializing — joblib/pickle execute arbitrary
    # code on load, so a tampered file must be rejected before that happens.
    from ml.runtime.artifact_integrity import verify_artifact_checksum

    verify_artifact_checksum(model_path, _checksum_path(model_path))
    verify_artifact_checksum(encoder_path, _checksum_path(encoder_path))

    try:
        with install_runtime_aliases():
            model = joblib.load(model_path)
        label_encoder = joblib.load(encoder_path)
    except Exception as exc:  # pragma: no cover - wrapped by runtime guard
        raise RuntimeArtifactError(f"Unable to load runtime artifacts: {exc}") from exc

    model_feature_names = getattr(model, "feature_names_in_", None)
    if model_feature_names is not None and list(model_feature_names) != FEATURE_COLUMNS:
        raise RuntimeArtifactError(
            "Saved model feature names do not match canonical FEATURE_COLUMNS"
        )

    if not hasattr(label_encoder, "classes_"):
        raise RuntimeArtifactError("Saved label encoder is missing classes_")

    return model, label_encoder
