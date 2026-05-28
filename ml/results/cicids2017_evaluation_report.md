# CICIDS2017 Model Evaluation Report

## Dataset

- Test file: `ml\data\cicids2017_test.csv`
- Total test rows: `504151`
- Label column: `Attack Type`
- Model: `ml\saved_models\cicids2017_live_compatible_model.pkl`

## Test Label Distribution

```text
Attack Type
Normal Traffic    419012
DoS                64352
Port Scanning      18139
Brute Force         1830
Web Attacks          429
Bots                 389
```

## Overall Metrics

| Metric | Score |
|---|---:|
| Accuracy | 0.9983 |
| Precision | 0.9983 |
| Recall | 0.9983 |
| F1 Score | 0.9980 |

| Normal Traffic FPR | 0.0063 |

## Classification Report

```text
                precision    recall  f1-score   support

          Bots       0.94      0.68      0.79       389
   Brute Force       1.00      1.00      1.00      1830
           DoS       1.00      1.00      1.00     64352
Normal Traffic       1.00      1.00      1.00    419012
 Port Scanning       0.99      1.00      0.99     18139
   Web Attacks       0.95      0.13      0.22       429

      accuracy                           1.00    504151
     macro avg       0.98      0.80      0.83    504151
  weighted avg       1.00      1.00      1.00    504151

```

## Confusion Matrix

Labels order: ['Bots', 'Brute Force', 'DoS', 'Normal Traffic', 'Port Scanning', 'Web Attacks']

```text
[[   265      0      0    124      0      0]
 [     0   1828      0      2      0      0]
 [     0      0  64315     35      2      0]
 [    18      0     88 418712    191      3]
 [     0      0      9      5  18125      0]
 [     0      0      1    374      0     54]]
```
