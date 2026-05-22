import pandas as pd

from ml.datasets.dataset_loader import DatasetLoader


class NSLKDDLoader(DatasetLoader):
    LABEL_COLUMN = "label"

    COLUMNS = [
        "duration",
        "protocol_type",
        "service",
        "flag",
        "src_bytes",
        "dst_bytes",
        "land",
        "wrong_fragment",
        "urgent",
        "hot",
        "num_failed_logins",
        "logged_in",
        "num_compromised",
        "root_shell",
        "su_attempted",
        "num_root",
        "num_file_creations",
        "num_shells",
        "num_access_files",
        "num_outbound_cmds",
        "is_host_login",
        "is_guest_login",
        "count",
        "srv_count",
        "serror_rate",
        "srv_serror_rate",
        "rerror_rate",
        "srv_rerror_rate",
        "same_srv_rate",
        "diff_srv_rate",
        "srv_diff_host_rate",
        "dst_host_count",
        "dst_host_srv_count",
        "dst_host_same_srv_rate",
        "dst_host_diff_srv_rate",
        "dst_host_same_src_port_rate",
        "dst_host_srv_diff_host_rate",
        "dst_host_serror_rate",
        "dst_host_srv_serror_rate",
        "dst_host_rerror_rate",
        "dst_host_srv_rerror_rate",
        "label",
        "difficulty",
    ]

    def __init__(
        self,
        dataset_path: str,
        test_size: float = 0.2,
        random_state: int = 42,
        binary_classification: bool = True,
    ):
        super().__init__(
            dataset_path=dataset_path,
            label_column=self.LABEL_COLUMN,
            test_size=test_size,
            random_state=random_state,
        )
        self.binary_classification = binary_classification

    def load_csv(self) -> pd.DataFrame:
        df = pd.read_csv(self.dataset_path, names=self.COLUMNS)

        if df.empty:
            raise ValueError("NSL-KDD dataset is empty")

        return df

    def clean_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Drop NSL-KDD difficulty score. It is metadata, not a runtime feature.
        if "difficulty" in df.columns:
            df.drop(columns=["difficulty"], inplace=True)

        # Convert symbolic categorical columns using one-hot encoding.
        categorical_columns = [
            "protocol_type",
            "service",
            "flag",
        ]

        existing_categorical = [col for col in categorical_columns if col in df.columns]

        if existing_categorical:
            df = pd.get_dummies(
                df,
                columns=existing_categorical,
                drop_first=False,
            )

        df = super().clean_dataset(df)

        if self.binary_classification:
            df[self.label_column] = df[self.label_column].apply(
                lambda label: "normal" if label == "normal" else "attack"
            )

        return df
