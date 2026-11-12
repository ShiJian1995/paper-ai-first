"""Fetch public data and bind it to a source manifest and immutable content hash."""
import hashlib
from pathlib import Path
import re
from .common import WorkflowError, digest, event, identifier, inside, load, now, request_bytes, required, save


def fetch(root, manifest_path):
    root = Path(root)
    manifest = load(manifest_path)
    required(manifest, ["id", "url", "source_page", "license", "license_url", "kind", "description"], "dataset")
    key = identifier(manifest["id"])
    if manifest["kind"] not in ("observational", "simulation", "synthetic", "benchmark"):
        raise WorkflowError("kind must identify the nature of the data")
    if manifest["license"].lower() in ("unknown", "unverified", "todo"):
        raise WorkflowError("Resolve the data license before fetching")
    if manifest["kind"] in ("simulation", "synthetic"):
        required(manifest, ["generation_method", "limitations"], "generated data provenance")
    expected = manifest.get("sha256")
    if expected and not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise WorkflowError("sha256 must be a 64-character hexadecimal digest")
    limit = manifest.get("max_bytes", 50_000_000)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise WorkflowError("max_bytes must be a positive integer")
    registry_path = root / "research/datasets.json"
    registry = load(registry_path) if registry_path.exists() else {}
    previous = registry.get(key)
    # The first successful download pins the bytes locally. A later revision needs a new ID.
    if previous:
        old_expected = previous["sha256"]
        if expected and expected.lower() != old_expected:
            raise WorkflowError("Dataset ID already pins different bytes; use a new versioned ID")
        if previous["manifest"] != manifest:
            raise WorkflowError("Dataset ID already has a different manifest; use a new versioned ID")
        path = inside(root, previous["path"])
        if path.exists():
            if digest(path) != old_expected:
                raise WorkflowError("Cached data was modified; preserve it for inspection and restore the pinned version")
            return previous
        expected = old_expected
    body, final_url, headers = request_bytes(manifest["url"], max_bytes=limit)
    actual = hashlib.sha256(body).hexdigest()
    if expected and actual != expected.lower():
        raise WorkflowError(f"Checksum mismatch: expected {expected}, received {actual}; no data registered")
    if not body:
        raise WorkflowError("Empty dataset")
    relative = f"data/raw/{key}/{actual}.data"
    path = inside(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    record = {"id": key, "path": relative, "sha256": actual, "bytes": len(body), "retrieved_at": now(),
              "final_url": final_url, "etag": headers.get("ETag"), "manifest": manifest,
              "checksum_origin": "supplied" if manifest.get("sha256") else "first-download-local-pin"}
    registry[key] = record
    save(registry_path, registry)
    save(root / f"data/manifests/{key}.resolved.json", record)
    event(root, "dataset_fetched", {"id": key, "sha256": actual})
    return record


def verify_datasets(root, ids):
    registry = load(Path(root) / "research/datasets.json")
    result = {}
    if not ids:
        raise WorkflowError("Experiment must bind at least one registered input dataset")
    for key in ids:
        identifier(key)
        if key not in registry:
            raise WorkflowError(f"Dataset is not registered: {key}")
        item = registry[key]
        path = inside(root, item["path"])
        if not path.is_file() or digest(path) != item["sha256"]:
            raise WorkflowError(f"Missing or modified data: {key}")
        result[key] = item
    return result
