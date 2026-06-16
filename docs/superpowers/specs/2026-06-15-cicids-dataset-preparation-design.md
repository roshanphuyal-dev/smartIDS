# CICIDS2017 Dataset Preparation Design

## Goal

Create a reproducible command that converts verified raw CICIDS2017 CSV exports into strict canonical train and test datasets without modifying the source files.

## Inputs And Outputs

The command accepts either one CSV file or a directory of CSV files. Directory inputs are processed in sorted filename order.

It writes:

- `cicids2017_train.csv`;
- `cicids2017_test.csv`;
- `cicids2017_dataset_metadata.json`.

The generated CSVs contain exactly `FEATURE_COLUMNS` followed by `LABEL_COLUMN`.

## Validation And Splitting

Raw headers are mapped through the canonical CICIDS2017 mapping. Every canonical feature must exist and contain finite numeric values. Labels are normalized centrally.

The split is stratified by normalized label with configurable test size and random seed. Existing generated files are not overwritten unless `--force` is supplied.

## Metadata

Metadata records the source file hashes and row counts, output hashes and row counts, canonical feature order, label distributions, test size, and random seed.

## Failure Safety

All source files are loaded and validated before output files are written. Missing or invalid canonical fields therefore leave the output directory unchanged.

