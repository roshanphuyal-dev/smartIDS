# Strict CICIDS2017 Dataset Validation Design

## Goal

Use one strict validation path for live-compatible CICIDS2017 training and evaluation so schema drift or invalid numeric values cannot be hidden by zero-filling.

## Validation Contract

The shared validator will:

- normalize raw CICIDS2017 headers through `CICIDS2017_TO_INTERNAL`;
- require every field in `FEATURE_COLUMNS`;
- ignore extra dataset columns;
- select features in exactly canonical order;
- reject non-numeric, NaN, positive infinity, and negative infinity values;
- return a copied dataframe so callers do not mutate source data.

Training and evaluation remain responsible for their own label encoding and artifact handling.

## Error Handling

Validation errors will identify missing or invalid canonical field names. Dataset repair or regeneration remains explicit; no missing or invalid value will be replaced with `0`.

## Testing

Tests will cover canonical ordering, ignored extras, missing fields, non-numeric values, NaN, and infinity. Integration-level preparation tests will confirm both training and evaluation use the shared validator.

