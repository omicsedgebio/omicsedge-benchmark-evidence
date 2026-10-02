"""Bounded metadata discovery through the public ENA Portal API."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

from .models import DiscoveryResult, PilotTaxon, RequestSnapshot
from .provenance import sha256_bytes


ENA_BASE_URL = "https://www.ebi.ac.uk/ena/portal/api"
RESULT_TYPE = "read_run"

# Deterministic and intentionally metadata-only. File URLs/checksums/sizes are
# recorded, but this module never follows a returned sequencing-file URL.
READ_RUN_FIELDS = (
    "run_accession",
    "experiment_accession",
    "study_accession",
    "secondary_study_accession",
    "sample_accession",
    "secondary_sample_accession",
    "tax_id",
    "scientific_name",
    "library_strategy",
    "library_source",
    "library_selection",
    "library_layout",
    "instrument_platform",
    "instrument_model",
    "read_count",
    "base_count",
    "first_public",
    "fastq_ftp",
    "fastq_md5",
    "fastq_bytes",
    "submitted_ftp",
    "submitted_md5",
    "submitted_bytes",
)


class EnaApiError(RuntimeError):
    """A non-recoverable ENA request or response failure."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


Transport = Callable[[str, Mapping[str, Any], float], HttpResponse]
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _default_transport(endpoint: str, parameters: Mapping[str, Any], timeout: float) -> HttpResponse:
    url = f"{endpoint}?{urlencode(parameters)}"
    request = Request(url, headers={"Accept": "application/json, text/tab-separated-values"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS API endpoint
            headers: Message = response.headers
            return HttpResponse(
                status=response.status,
                body=response.read(),
                headers={key.lower(): value for key, value in headers.items()},
            )
    except HTTPError as exc:
        body = exc.read()
        return HttpResponse(
            status=exc.code,
            body=body,
            headers={key.lower(): value for key, value in exc.headers.items()},
        )
    except (TimeoutError, URLError) as exc:
        raise EnaApiError(f"ENA request failed: {url}: {exc}") from exc


class EnaAdapter:
    """ENA ``read_run`` adapter with bounded requests and request provenance.

    M1A intentionally uses one bounded ``limit`` query per taxon. ENA also
    documents ``limit=0`` for all matches, but M1A never requests an unbounded
    archive response. Deterministic temporal partitioning is deferred to M1B.
    """

    source_id = "ena"

    def __init__(
        self,
        *,
        base_url: str = ENA_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 4,
        backoff_seconds: float = 0.5,
        min_interval_seconds: float = 0.1,
        transport: Transport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Clock = _utc_now,
    ) -> None:
        if timeout <= 0 or max_retries < 0 or backoff_seconds < 0 or min_interval_seconds < 0:
            raise ValueError("invalid ENA request timing configuration")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.min_interval_seconds = min_interval_seconds
        self.transport = transport or _default_transport
        self.sleeper = sleeper
        self.clock = clock
        self._last_request_monotonic: float | None = None
        self._introspection_cache: tuple[Sequence[str], Sequence[str]] | None = None

    def _request(
        self,
        path: str,
        parameters: Mapping[str, Any],
        *,
        record_count: Callable[[bytes], int],
        pagination: Mapping[str, Any],
    ) -> RequestSnapshot:
        endpoint = f"{self.base_url}/{path.lstrip('/')}"
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            if self._last_request_monotonic is not None and self.min_interval_seconds:
                elapsed = time.monotonic() - self._last_request_monotonic
                if elapsed < self.min_interval_seconds:
                    self.sleeper(self.min_interval_seconds - elapsed)
            try:
                response = self.transport(endpoint, parameters, self.timeout)
            except EnaApiError as exc:
                response = None
                last_error = str(exc)
            self._last_request_monotonic = time.monotonic()
            if response is not None and response.status == 200:
                try:
                    count = record_count(response.body)
                except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                    last_error = f"malformed ENA response from {endpoint}: {exc}"
                    if attempt >= self.max_retries:
                        raise EnaApiError(last_error) from exc
                    delay = self.backoff_seconds * (2**attempt) + random.uniform(0, 0.05)
                    self.sleeper(delay)
                    continue
                else:
                    return RequestSnapshot(
                        source=self.source_id,
                        endpoint=endpoint,
                        parameters=dict(parameters),
                        retrieved_at=_timestamp(self.clock()),
                        http_status=response.status,
                        response_sha256=sha256_bytes(response.body),
                        record_count=count,
                        pagination=dict(pagination),
                        response_body=response.body,
                        content_type=response.headers.get("content-type"),
                    )
            status = response.status if response is not None else None
            if status is not None and status not in {408, 425, 429, 500, 502, 503, 504}:
                snippet = response.body.decode("utf-8", errors="replace")[:300]
                raise EnaApiError(f"ENA HTTP {status} from {endpoint}: {snippet}")
            last_error = last_error or f"ENA HTTP {status} from {endpoint}"
            if attempt < self.max_retries:
                retry_after = None if response is None else response.headers.get("retry-after")
                try:
                    delay = float(retry_after) if retry_after is not None else None
                except ValueError:
                    delay = None
                if delay is None:
                    # Bounded jitter prevents synchronized retries while tests can
                    # inject a no-op sleeper. Randomness never enters output data.
                    delay = self.backoff_seconds * (2**attempt) + random.uniform(0, 0.05)
                self.sleeper(delay)
        raise EnaApiError(last_error or f"ENA request failed: {endpoint}")

    @staticmethod
    def _tsv_rows(body: bytes) -> list[dict[str, str]]:
        text = body.decode("utf-8")
        lines = text.splitlines()
        if not lines:
            raise ValueError("empty TSV response")
        header = lines[0].split("\t")
        if not header or any(not field for field in header):
            raise ValueError("invalid TSV header")
        rows: list[dict[str, str]] = []
        for line_number, line in enumerate(lines[1:], start=2):
            if not line:
                continue
            values = line.split("\t")
            if len(values) != len(header):
                raise ValueError(f"TSV row {line_number} has {len(values)} columns; expected {len(header)}")
            rows.append(dict(zip(header, values)))
        return rows

    @classmethod
    def _tsv_count(cls, body: bytes) -> int:
        return len(cls._tsv_rows(body))

    @staticmethod
    def _introspection_rows(body: bytes) -> list[dict[str, str]]:
        """Parse ENA field metadata, including its empty-description rows.

        The live API omits the empty middle cell for some rows (for example
        ``aligned<TAB>boolean``) even though the header is
        ``columnId<TAB>description<TAB>type``. The two-column form is
        unambiguous because the final value is the declared field type.
        Search result TSV remains strict and is parsed by ``_tsv_rows``.
        """

        lines = body.decode("utf-8").splitlines()
        if not lines or lines[0].split("\t") != ["columnId", "description", "type"]:
            raise ValueError("unexpected ENA introspection header")
        rows: list[dict[str, str]] = []
        for line_number, line in enumerate(lines[1:], start=2):
            if not line:
                continue
            values = line.split("\t")
            if len(values) == 2:
                values = [values[0], "", values[1]]
            if len(values) != 3:
                raise ValueError(f"introspection row {line_number} has {len(values)} columns")
            rows.append(dict(zip(("columnId", "description", "type"), values)))
        return rows

    @classmethod
    def _introspection_count(cls, body: bytes) -> int:
        return len(cls._introspection_rows(body))

    @staticmethod
    def _parse_count(body: bytes) -> int:
        lines = body.decode("utf-8").splitlines()
        if len(lines) != 2 or lines[0] != "count":
            raise ValueError("unexpected ENA count response")
        count = int(lines[1])
        if count < 0:
            raise ValueError("negative ENA count")
        return count

    def introspect(self) -> tuple[Sequence[str], Sequence[str], list[RequestSnapshot]]:
        if self._introspection_cache is not None:
            return self._introspection_cache[0], self._introspection_cache[1], []
        requests: list[RequestSnapshot] = []
        values: list[list[str]] = []
        for path in ("returnFields", "searchFields"):
            snapshot = self._request(
                path,
                {"result": RESULT_TYPE},
                record_count=self._introspection_count,
                pagination={"kind": "not_applicable"},
            )
            rows = self._introspection_rows(snapshot.response_body)
            if not rows or "columnId" not in rows[0]:
                raise EnaApiError(f"ENA {path} response lacks columnId")
            values.append([row["columnId"] for row in rows])
            requests.append(snapshot)
        missing_return = sorted(set(READ_RUN_FIELDS) - set(values[0]))
        if missing_return:
            raise EnaApiError(f"ENA read_run no longer declares required return fields: {missing_return}")
        if "tax_id" not in values[1]:
            raise EnaApiError("ENA read_run no longer declares tax_id as searchable")
        self._introspection_cache = (values[0], values[1])
        return values[0], values[1], requests

    def discover(self, taxon: PilotTaxon, *, limit: int) -> DiscoveryResult:
        if not 1 <= limit <= 100:
            raise ValueError("M1A ENA discovery limit must be between 1 and 100")
        return_fields, search_fields, requests = self.introspect()
        query = f"tax_eq({taxon.taxon_id})" if taxon.query_mode == "exact" else f"tax_tree({taxon.taxon_id})"

        count_snapshot = self._request(
            "count",
            {"result": RESULT_TYPE, "query": query},
            record_count=self._parse_count,
            pagination={"kind": "aggregate", "enumerated": False},
        )
        source_count = count_snapshot.record_count
        requests.append(count_snapshot)

        search_parameters = {
            "result": RESULT_TYPE,
            "query": query,
            "fields": ",".join(READ_RUN_FIELDS),
            "format": "tsv",
            "limit": limit,
        }
        search_snapshot = self._request(
            "search",
            search_parameters,
            record_count=self._tsv_count,
            pagination={
                "kind": "bounded_single_page",
                "page": 1,
                "limit": limit,
                "continuation_supported": False,
                "reason": "M1A intentionally uses one bounded limit query; deterministic temporal partitioning is deferred to M1B",
            },
        )
        rows = self._tsv_rows(search_snapshot.response_body)
        if len(rows) > limit:
            raise EnaApiError(f"ENA returned {len(rows)} records for limit={limit}")
        requests.append(search_snapshot)
        return DiscoveryResult(
            taxon=taxon,
            source_reported_count=source_count,
            records=rows,
            requests=requests,
            return_fields=return_fields,
            search_fields=search_fields,
            pagination_note="Bounded limit query; full/incremental temporal partitioning is deferred to M1B.",
        )


class FixtureTransport:
    """Offline ENA transport using small captured TSV fixtures."""

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    def __call__(self, endpoint: str, parameters: Mapping[str, Any], timeout: float) -> HttpResponse:
        del timeout
        path = endpoint.rsplit("/", 1)[-1]
        if path in {"returnFields", "searchFields"}:
            filename = "return_fields.tsv" if path == "returnFields" else "search_fields.tsv"
        elif path in {"count", "search"}:
            query = str(parameters.get("query", ""))
            match = re.fullmatch(r"tax_(eq|tree)\(([0-9]+)\)", query)
            if not match:
                return HttpResponse(400, b"unsupported fixture query\n", {"content-type": "text/plain"})
            mode = "exact" if match.group(1) == "eq" else "tree"
            suffix = "count" if path == "count" else "search"
            filename = f"{suffix}_{match.group(2)}_{mode}.tsv"
        else:
            return HttpResponse(404, b"unknown fixture endpoint\n", {"content-type": "text/plain"})
        fixture = self.fixture_dir / filename
        if not fixture.is_file():
            return HttpResponse(404, f"missing fixture {filename}\n".encode(), {"content-type": "text/plain"})
        return HttpResponse(200, fixture.read_bytes(), {"content-type": "text/tab-separated-values"})
