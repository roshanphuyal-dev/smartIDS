"""Generate/update SHA-256 checksum sidecar files for saved ML model artifacts.

Walks ``ml/saved_models/**/*.pkl`` and writes a sibling ``<filename>.sha256``
file for each one, in the conventional ``sha256sum``-compatible single-line
hex-digest format expected by ``ml.runtime.artifact_integrity.verify_artifact_checksum``.

Usage:
    python -m ml.runtime.generate_artifact_checksums
"""

from __future__ import annotations

from pathlib import Path

from ml.runtime.artifact_integrity import compute_sha256

REPO_ROOT = Path(__file__).resolve().parents[2]
SAVED_MODELS_DIR = REPO_ROOT / "ml" / "saved_models"
ARTIFACT_GLOB = "**/*.pkl"


def generate_checksums(saved_models_dir: Path = SAVED_MODELS_DIR) -> list[Path]:
    """Write/update ``.sha256`` sidecar files for every artifact under ``saved_models_dir``.

    Returns the list of artifact paths that were checksummed.
    """
    if not saved_models_dir.exists():
        print(f"No saved_models directory found at {saved_models_dir}; nothing to do.")
        return []

    updated: list[Path] = []
    for artifact_path in sorted(saved_models_dir.glob(ARTIFACT_GLOB)):
        if not artifact_path.is_file():
            continue

        checksum = compute_sha256(artifact_path)
        checksum_path = artifact_path.with_name(artifact_path.name + ".sha256")
        checksum_path.write_text(f"{checksum}\n", encoding="utf-8")
        updated.append(artifact_path)
        print(f"Wrote {checksum_path.relative_to(saved_models_dir.parent)}")

    return updated


def main() -> None:
    updated = generate_checksums()
    print(f"Updated {len(updated)} checksum file(s).")


if __name__ == "__main__":
    main()
