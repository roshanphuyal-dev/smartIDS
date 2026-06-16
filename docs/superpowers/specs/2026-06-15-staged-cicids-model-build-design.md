# Staged CICIDS2017 Model Build Design

## Goal

Provide one command that validates prepared datasets, trains the live-compatible model, evaluates it, verifies runtime loading and prediction, writes complete handoff artifacts, and activates them only after every check passes.

## Command

The command is:

```powershell
.\.venv_windows\Scripts\python.exe -m ml.training.build_cicids2017_model
```

Defaults point to the generated train, test, and dataset metadata files under `ml/data` and activate verified artifacts under `ml/saved_models`.

## Staging And Activation

The command builds in a temporary sibling directory on the same filesystem as the active model directory. Existing active files are copied into staging so unrelated artifacts remain intact.

After training, evaluation, manifest creation, runtime artifact validation, and sample prediction all pass, the active directory is renamed to a backup and staging is renamed into place. If activation fails, the backup is restored. Failed builds never modify active artifacts.

## Inputs

Training and evaluation inputs must contain exactly the canonical live-compatible feature contract after mapping:

- all fields in `FEATURE_COLUMNS`;
- finite numeric values only;
- CICIDS duration and IAT fields converted from microseconds to live-runtime seconds;
- `Attack Type` labels normalized through the canonical label mapping;
- dataset metadata whose feature order, row counts, and train/test hashes match the files.

## Outputs

The activated directory contains:

- `cicids2017_live_compatible_model.pkl`;
- `live_compatible_label_encoder.pkl`;
- `live_compatible_feature_columns.json`;
- `live_compatible_benchmark_report.json`;
- `cicids2017_evaluation_report.md`;
- `live_compatible_training_metadata.json`;
- `live_compatible_model_manifest.json`;
- `live_compatible_sample_input.json`;
- `live_compatible_sample_output.json`.

The manifest records model type, class labels, canonical schema, dataset provenance, metrics, and hashes for all activated artifacts.

## Runtime Verification

Before activation, the staged model, encoder, and feature schema are loaded through `load_runtime_model_artifacts`. A real sample row is then predicted using the runtime input ordering and output shape:

```json
{
  "label": "Normal Traffic",
  "confidence": 0.99,
  "encoded": 3
}
```

## Failure Behavior

Missing datasets, metadata mismatches, unknown test labels, training errors, invalid artifacts, prediction errors, or activation errors stop the command. Existing active artifacts remain available.
