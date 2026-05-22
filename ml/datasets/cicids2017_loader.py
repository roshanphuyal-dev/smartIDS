from pathlib import Path
from typing import List, Optional

import pandas as pd  # type: ignore

from ml.datasets.dataset_loader import DatasetLoader


class CICIDS2017Loader(DatasetLoader):
    DEFAULT_LABEL_COLUMN = "Attack Type"

    def __init__(
        self,
        dataset_path: str,
        test_size: float = 0.2,
        random_state: int = 42,
        binary_classification: bool = True,
    ):
        super().__init__(
            dataset_path=dataset_path,
            label_column=self.DEFAULT_LABEL_COLUMN,
            test_size=test_size,
            random_state=random_state,
        )
        self.binary_classification = binary_classification

    def load_csv(self) -> pd.DataFrame:
        path = Path(self.dataset_path)

        if path.is_file():
            return super().load_csv()

        if path.is_dir():
            csv_files = list(path.glob("*.csv"))

            if not csv_files:
                raise FileNotFoundError(f"No CSV files found in: {path}")

            frames: List[pd.DataFrame] = []

            for csv_file in csv_files:
                df = pd.read_csv(csv_file)
                df.columns = [col.strip() for col in df.columns]
                frames.append(df)

            merged_df = pd.concat(frames, axis=0, ignore_index=True)

            if self.label_column not in merged_df.columns:
                raise ValueError(
                    f"Label column '{self.label_column}' not found in merged CICIDS2017 files"
                )

            return merged_df

        raise FileNotFoundError(f"Dataset path not found: {path}")

    def clean_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        df = super().clean_dataset(df)

        if self.binary_classification:
            # This repo's CICIDS2017 CSVs commonly use "Normal Traffic" for
            # benign rows (see ml/data/cicids2017_*.csv). Normalize a few common
            # variants to avoid collapsing everything into "attack".
            benign_labels = {
                "benign",
                "normal",
                "normal traffic",
            }

            def to_binary(label: object) -> str:
                s = str(label).strip().lower()
                if s in benign_labels or s.startswith("normal") or s.startswith("benign"):
                    return "benign"
                return "attack"

            df[self.label_column] = df[self.label_column].apply(to_binary)

        return df
