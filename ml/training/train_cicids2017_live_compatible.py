from pathlib import Path
import json
from datetime import datetime, timezone

import joblib
import pandas as pd

from ml.evaluation.metrics import MetricsEvaluator
from ml.models.sklearn_model import SklearnModel
from ml.models.xgboost_model import XGBoostModel

from ml.features.schema import FEATURE_COLUMNS, LABEL_COLUMN
from ml.features.cicids2017_mapping import normalize_cicids2017_label
from ml.features.cicids2017_validation import prepare_cicids2017_features


DATASET_PATH = Path("ml/data/cicids2017_train.csv")
MODEL_OUTPUT_DIR = Path("ml/saved_models")
MODEL_TYPE = "xgboost"
TEST_SIZE = 0.2
RANDOM_STATE = 42


def _load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    if path.is_file():
        df = pd.read_csv(path)
        df.columns = [col.strip() for col in df.columns]
        return df

    csv_files = sorted(path.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in: {path}")

    frames = []
    for csv_file in csv_files:
        frame = pd.read_csv(csv_file)
        frame.columns = [col.strip() for col in frame.columns]
        frames.append(frame)

    return pd.concat(frames, axis=0, ignore_index=True)


def _prepare_live_compatible_dataset(df: pd.DataFrame):
    if LABEL_COLUMN not in df.columns:
        raise ValueError(f"Label column '{LABEL_COLUMN}' not found in dataset")

    X = prepare_cicids2017_features(df)

    y_raw = df[LABEL_COLUMN].apply(normalize_cicids2017_label).astype(str)
    label_encoder = joblib.load(MODEL_OUTPUT_DIR / "label_encoder.pkl") if (MODEL_OUTPUT_DIR / "label_encoder.pkl").exists() else None

    if label_encoder is None:
        from sklearn.preprocessing import LabelEncoder

        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(y_raw)
    else:
        unknown = set(y_raw.unique()) - set(label_encoder.classes_)
        if unknown:
            raise ValueError(f"Unknown labels found for existing encoder: {sorted(unknown)}")
        y = label_encoder.transform(y_raw)

    return X, y, label_encoder


def train():
    print("Loading CICIDS2017 dataset...")
    df = _load_dataset(DATASET_PATH)

    print("Preparing live-compatible feature set...")
    X, y, label_encoder = _prepare_live_compatible_dataset(df)

    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    if MODEL_TYPE == "xgboost":
        model_wrapper = XGBoostModel()
    else:
        model_wrapper = SklearnModel(model_type=MODEL_TYPE)

    print("Training model...")
    model_wrapper.train(X_train, y_train)

    print("Evaluating model...")
    predictions = model_wrapper.predict(X_test)

    labels = list(range(len(label_encoder.classes_)))
    target_names = [str(label) for label in label_encoder.classes_]

    evaluator = MetricsEvaluator()
    metrics = evaluator.evaluate(
        y_true=y_test,
        y_pred=predictions,
        labels=labels,
        target_names=target_names,
    )
    evaluator.print_summary(metrics)

    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODEL_OUTPUT_DIR / "cicids2017_live_compatible_model.pkl"
    label_encoder_path = MODEL_OUTPUT_DIR / "live_compatible_label_encoder.pkl"
    feature_columns_path = MODEL_OUTPUT_DIR / "live_compatible_feature_columns.json"
    report_path = MODEL_OUTPUT_DIR / "live_compatible_benchmark_report.json"
    metadata_path = MODEL_OUTPUT_DIR / "live_compatible_training_metadata.json"

    model_wrapper.save(str(model_path))
    joblib.dump(label_encoder, label_encoder_path)

    with open(feature_columns_path, "w", encoding="utf-8") as file:
        json.dump(FEATURE_COLUMNS, file, indent=4)

    evaluator.save_report(metrics=metrics, output_path=str(report_path))

    metadata = {
        "model_file": str(model_path),
        "label_encoder_file": str(label_encoder_path),
        "feature_columns_file": str(feature_columns_path),
        "protocol_encoding": {"TCP": 6, "UDP": 17, "ICMP": 1, "UNKNOWN": 0},
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    with open(metadata_path, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4)

    print("Training complete.")


if __name__ == "__main__":
    train()
