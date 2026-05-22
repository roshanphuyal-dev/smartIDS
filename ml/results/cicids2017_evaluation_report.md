# CICIDS2017 Model Evaluation Report

## Dataset

- Test file: `ml/data/cicids2017_test.csv`
- Total test rows: `504151`
- Label column: `Attack Type`
- Model: `ml/saved_models/cicids2017_model.pkl`

## Test Label Distribution

```text
Attack Type
benign    419012
attack     85139
```

## Overall Metrics

| Metric | Score |
|---|---:|
| Accuracy | 0.9992 |
| Precision | 0.9992 |
| Recall | 0.9992 |
| F1 Score | 0.9992 |

## Classification Report

```text
              precision    recall  f1-score   support

      attack       1.00      1.00      1.00     85139
      benign       1.00      1.00      1.00    419012

    accuracy                           1.00    504151
   macro avg       1.00      1.00      1.00    504151
weighted avg       1.00      1.00      1.00    504151

```

## Confusion Matrix

Labels order: ['attack', 'benign']

```text
[[ 84982    157]
 [   268 418744]]
```
