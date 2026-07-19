"""Pre-load integrity verification for ML runtime artifacts.

Computes and verifies SHA-256 checksums for model/encoder files so that a
tampered artifact is rejected before it is ever deserialized (joblib/pickle
execute arbitrary code on load, so this check must run first).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ml.runtime.artifact_validation import RuntimeArtifactError

_CHUNK_SIZE = 65536


def compute_sha256(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of the file at ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact_checksum(path: Path, checksum_path: Path) -> None:
    """Verify that ``path`` matches the checksum recorded at ``checksum_path``.

    Raises ``RuntimeArtifactError`` if the checksum file is missing/unreadable
    or if the computed digest does not match the recorded one.
    """
    if not checksum_path.exists():
        raise RuntimeArtifactError(f"Missing checksum file for artifact: {checksum_path}")

    try:
        checksum_contents = checksum_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeArtifactError(f"Unable to read checksum file: {checksum_path}") from exc

    expected_checksum = checksum_contents.strip().split()[0] if checksum_contents.strip() else ""
    if not expected_checksum:
        raise RuntimeArtifactError(f"Checksum file is empty: {checksum_path}")

    actual_checksum = compute_sha256(path)
    if actual_checksum.lower() != expected_checksum.lower():
        raise RuntimeArtifactError(
            f"Checksum mismatch for artifact {path}: expected {expected_checksum}, got {actual_checksum}"
        )
