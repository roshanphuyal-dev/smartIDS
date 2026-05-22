from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split

DATASET_PATH = Path("ml/data/cicids2017_cleaned.csv")
OUTPUT_DIR = Path("ml/data")
LABEL_COLUMN = "Attack Type"

TRAIN_PATH = OUTPUT_DIR / "cicids2017_train.csv"
TEST_PATH = OUTPUT_DIR / "cicids2017_test.csv"


def main():
    df = pd.read_csv(DATASET_PATH)

    if LABEL_COLUMN not in df.columns:
        raise ValueError(f"Label column '{LABEL_COLUMN}' not found.")

    train_df, test_df = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
        stratify=df[LABEL_COLUMN],
    )

    train_df.to_csv(TRAIN_PATH, index=False)
    test_df.to_csv(TEST_PATH, index=False)

    print(f"Training file saved: {TRAIN_PATH}")
    print(f"Testing file saved: {TEST_PATH}")
    print(f"Train rows: {len(train_df)}")
    print(f"Test rows: {len(test_df)}")


if __name__ == "__main__":
    main()