"""Source-neutral contracts for bounded catalog discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class PilotTaxon:
    """One bounded taxonomic discovery scope."""

    taxon_id: int
    scientific_name: str
    query_mode: str = "exact"

    def __post_init__(self) -> None:
        if self.taxon_id < 1:
            raise ValueError("taxon_id must be positive")
        if self.query_mode not in {"exact", "tree"}:
            raise ValueError("query_mode must be 'exact' or 'tree'")


@dataclass(frozen=True)
class RequestSnapshot:
    """Audit metadata for one HTTP response body."""

    source: str
    endpoint: str
    parameters: Mapping[str, Any]
    retrieved_at: str
    http_status: int
    response_sha256: str
    record_count: int
    pagination: Mapping[str, Any]
    response_body: bytes = field(repr=False)
    content_type: str | None = None

    def manifest_entry(self, snapshot_path: str) -> dict[str, Any]:
        return {
            "source": self.source,
            "endpoint": self.endpoint,
            "parameters": dict(sorted(self.parameters.items())),
            "retrieved_at": self.retrieved_at,
            "http_status": self.http_status,
            "response_sha256": self.response_sha256,
            "record_count": self.record_count,
            "pagination": dict(self.pagination),
            "content_type": self.content_type,
            "snapshot_path": snapshot_path,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    """One source adapter's bounded discovery result."""

    taxon: PilotTaxon
    source_reported_count: int
    records: Sequence[Mapping[str, Any]]
    requests: Sequence[RequestSnapshot]
    return_fields: Sequence[str]
    search_fields: Sequence[str]
    pagination_note: str


class CatalogAdapter(Protocol):
    """Contract reusable by future metadata source adapters."""

    source_id: str

    def discover(self, taxon: PilotTaxon, *, limit: int) -> DiscoveryResult:
        """Return source count and at most ``limit`` metadata records."""

