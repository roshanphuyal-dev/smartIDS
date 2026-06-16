# Canonical Legacy CICIDS2017 Training Design

## Goal

Keep `python3 -m ml.training.train_cicids2017` supported while ensuring it trains only on the canonical live-compatible `FEATURE_COLUMNS` contract.

## Data Preparation

`CICIDS2017Loader` will normalize raw dataset column names through `CICIDS2017_TO_INTERNAL` before feature selection. The loader will require every field in `FEATURE_COLUMNS`, reject datasets with missing canonical fields using an error that lists those fields, and return features in exactly the canonical order.

Extra dataset columns will be ignored. The loader will no longer infer the training feature set from whichever numeric columns happen to remain after cleaning.

## Labels And Artifacts

The existing legacy binary label normalization and artifact filenames remain unchanged. The saved `feature_columns.json` file will contain exactly `FEATURE_COLUMNS`, matching runtime extraction and prediction order.

## Error Handling

Missing canonical columns are treated as dataset or mapping errors. Training will fail before model fitting instead of silently adding constant zero columns.

## Testing

Focused unit tests will verify:

- raw CICIDS2017 columns map into canonical internal names;
- feature output uses exactly `FEATURE_COLUMNS` in canonical order;
- extra columns are ignored;
- missing canonical columns produce a clear error listing the missing fields.

