"""Deterministic serialization and hashing helpers for catalog snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parameters_sha256(parameters: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(dict(sorted(parameters.items()))))


def file_manifest(paths: Iterable[Path], root: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(paths):
        data = path.read_bytes()
        entries.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_bytes(data),
                "size_bytes": len(data),
            }
        )
    return entries
