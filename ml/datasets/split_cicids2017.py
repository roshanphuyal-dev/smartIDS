from pathlib import Path

from ml.datasets.prepare_cicids2017 import prepare_dataset

DATASET_PATH = Path("ml/data/cicids2017_cleaned.csv")
OUTPUT_DIR = Path("ml/data")


def main():
    result = prepare_dataset(
        source=DATASET_PATH,
        output_dir=OUTPUT_DIR,
        force=True,
    )

    print(f"Training dataset: {result.train_path}")
    print(f"Testing dataset: {result.test_path}")
    print(f"Metadata: {result.metadata_path}")


if __name__ == "__main__":
    main()
