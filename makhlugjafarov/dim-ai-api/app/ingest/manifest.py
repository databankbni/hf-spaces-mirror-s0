from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.ingest.models import CorpusManifest, IngestionWarning


class ManifestError(ValueError):
    """Raised when a corpus manifest is invalid or unsafe to ingest."""


def load_manifest(path: Path, *, require_files: bool = True, allow_tbd: bool = False) -> CorpusManifest:
    manifest_path = path.expanduser().resolve()
    if not manifest_path.exists():
        raise ManifestError(f"Manifest does not exist: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if not isinstance(raw, dict):
        raise ManifestError("Manifest must be a YAML mapping")

    try:
        manifest = CorpusManifest.model_validate(raw)
    except ValidationError as exc:
        raise ManifestError(str(exc)) from exc

    warnings = validate_manifest(manifest, manifest_path.parent, require_files=require_files, allow_tbd=allow_tbd)
    errors = [warning for warning in warnings if warning.severity == "error"]
    if errors:
        details = "; ".join(f"{warning.source_id}: {warning.message}" for warning in errors)
        raise ManifestError(details)

    return _resolve_source_paths(manifest, manifest_path.parent)


def validate_manifest(
    manifest: CorpusManifest,
    manifest_dir: Path,
    *,
    require_files: bool,
    allow_tbd: bool,
) -> list[IngestionWarning]:
    warnings: list[IngestionWarning] = []
    seen_ids: set[str] = set()

    for source in manifest.sources:
        if source.source_id in seen_ids:
            warnings.append(_warning(source.source_id, "duplicate_source_id", "Source IDs must be unique.", "error"))
        seen_ids.add(source.source_id)

        if source.legal_status in {"TBD", "do_not_ingest"} and not allow_tbd:
            warnings.append(
                _warning(
                    source.source_id,
                    "unsafe_legal_status",
                    f"Source legal_status={source.legal_status!r} is not ingestible.",
                    "error",
                )
            )

        source_path = _resolve_path(source.path, manifest_dir)
        if require_files and not source_path.exists():
            warnings.append(_warning(source.source_id, "missing_source_file", f"Source file is missing: {source_path}", "error"))

    return warnings


def _resolve_source_paths(manifest: CorpusManifest, manifest_dir: Path) -> CorpusManifest:
    data: dict[str, Any] = manifest.model_dump(mode="python")
    for source in data["sources"]:
        source["path"] = _resolve_path(source["path"], manifest_dir)
    return CorpusManifest.model_validate(data)


def _resolve_path(path: Path, manifest_dir: Path) -> Path:
    if path.is_absolute():
        return path
    return (manifest_dir / path).resolve()


def _warning(source_id: str, code: str, message: str, severity: str) -> IngestionWarning:
    return IngestionWarning(source_id=source_id, severity=severity, code=code, message=message)
