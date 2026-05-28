import math
from statistics import mean, pstdev, pvariance


def safe_min(values) -> float:
    if not values:
        return 0.0
    return float(min(values))


def safe_max(values) -> float:
    if not values:
        return 0.0
    return float(max(values))


def safe_mean(values) -> float:
    if not values:
        return 0.0
    return float(mean(values))


def safe_std(values) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return 0.0
    return float(pstdev(values))


def safe_variance(values) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return 0.0
    return float(pvariance(values))


def safe_rate(value, duration) -> float:
    if duration is None or duration <= 0:
        return 0.0
    return float(value) / float(duration)


def safe_iat_stats(timestamps) -> dict:
    if not timestamps or len(timestamps) < 2:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "total": 0.0,
        }

    ordered = sorted(float(ts) for ts in timestamps)
    iats = [ordered[i] - ordered[i - 1] for i in range(1, len(ordered))]

    cleaned_iats = [iat for iat in iats if iat >= 0 and math.isfinite(iat)]

    if not cleaned_iats:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "total": 0.0,
        }

    return {
        "min": safe_min(cleaned_iats),
        "max": safe_max(cleaned_iats),
        "mean": safe_mean(cleaned_iats),
        "std": safe_std(cleaned_iats),
        "total": float(sum(cleaned_iats)),
    }


def sanitize_feature_dict(features) -> dict:
    sanitized = {}

    for key, value in features.items():
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            sanitized[key] = 0.0
            continue

        if not math.isfinite(numeric_value):
            sanitized[key] = 0.0
            continue

        sanitized[key] = numeric_value

    return sanitized
