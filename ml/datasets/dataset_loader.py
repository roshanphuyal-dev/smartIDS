import json
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder


class DatasetLoader:
    def __init__(
        self,
        dataset_path: str,
        label_column: str,
        test_size: float = 0.2,
        random_state: int = 42,
    ):
        self.dataset_path = Path(dataset_path)
        self.label_column = label_column
        self.test_size = test_size
        self.random_state = random_state
        self.label_encoder = LabelEncoder()
        self.feature_columns = []

    def load_csv(self) -> pd.DataFrame:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")

        df = pd.read_csv(self.dataset_path)

        if df.empty:
            raise ValueError("Dataset is empty")

        df.columns = [col.strip() for col in df.columns]

        if self.label_column not in df.columns:
            raise ValueError(
                f"Label column '{self.label_column}' not found. "
                f"Available columns: {list(df.columns)}"
            )

        return df

    def clean_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # strip whitespace
        df.columns = [col.strip() for col in df.columns]

        # remove duplicate rows
        df.drop_duplicates(inplace=True)

        # replace inf values
        df.replace([np.inf, -np.inf], np.nan, inplace=True)

        # remove rows with missing labels
        df.dropna(subset=[self.label_column], inplace=True)

        # remove useless columns
        useless_columns = [
            "Flow ID",
            "Source IP",
            "Destination IP",
            "Timestamp",
            "SimillarHTTP",
        ]

        existing_useless = [col for col in useless_columns if col in df.columns]

        if existing_useless:
            df.drop(columns=existing_useless, inplace=True)

        # normalize label formatting
        df[self.label_column] = (
            df[self.label_column].astype(str).str.strip().str.lower()
        )

        # convert numeric-looking columns safely
        for col in df.columns:
            if col == self.label_column:
                continue

            df[col] = pd.to_numeric(df[col], errors="coerce")

        # remove rows with too many NaNs
        df.dropna(axis=0, inplace=True)

        # remove constant columns
        constant_columns = [
            col
            for col in df.columns
            if col != self.label_column
            and col not in self.feature_columns
            and df[col].nunique() <= 1
        ]

        if constant_columns:
            df.drop(columns=constant_columns, inplace=True)

        return df

    def split_features_labels(
        self, df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, np.ndarray]:
        y_raw = df[self.label_column].astype(str)
        X = df.drop(columns=[self.label_column])

        X = X.select_dtypes(include=["int64", "float64", "int32", "float32"])

        if X.empty:
            raise ValueError("No numeric feature columns found after preprocessing")

        self.feature_columns = list(X.columns)
        y = self.label_encoder.fit_transform(y_raw)

        return X, y

    def train_test_split(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
        return train_test_split(
            X,
            y,
            test_size=self.test_size,
            random_state=self.random_state,
            stratify=y,
        )

    def load_and_prepare(self):
        df = self.load_csv()
        df = self.clean_dataset(df)

        X, y = self.split_features_labels(df)

        X_train, X_test, y_train, y_test = self.train_test_split(X, y)

        return X_train, X_test, y_train, y_test

    def save_feature_columns(self, output_path: str):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(self.feature_columns, file, indent=4)

    def get_label_encoder(self) -> LabelEncoder:
        return self.label_encoder
