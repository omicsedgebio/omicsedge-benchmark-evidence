from __future__ import annotations

import hashlib
import json
from typing import Mapping


IDENTITY_SCHEMA_VERSION = "phase1b-variant-identity-v1"

EXACT_NORMALIZED_ALLELE = "EXACT_NORMALIZED_ALLELE"
REPRESENTATION_EQUIVALENCE_SUPPORTED = "REPRESENTATION_EQUIVALENCE_SUPPORTED"
NON_EQUIVALENT = "NON_EQUIVALENT"
UNRESOLVED = "UNRESOLVED"

ALLOWED_IDENTITY_STATES = {
    EXACT_NORMALIZED_ALLELE,
    REPRESENTATION_EQUIVALENCE_SUPPORTED,
    NON_EQUIVALENT,
    UNRESOLVED,
}


_REQUIRED_FIELDS = (
    "assembly",
    "contig",
    "start",
    "end",
    "ref",
    "alt",
)


def _validated_allele(
    allele: Mapping[str, object],
) -> dict[str, object]:
    missing = [
        field
        for field in _REQUIRED_FIELDS
        if field not in allele
    ]

    if missing:
        raise ValueError(
            "missing required allele fields: "
            + ", ".join(missing)
        )

    assembly = str(allele["assembly"]).strip()
    contig = str(allele["contig"]).strip()
    ref = str(allele["ref"]).strip()
    alt = str(allele["alt"]).strip()

    try:
        start = int(allele["start"])
        end = int(allele["end"])
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "start and end must be integers"
        ) from exc

    if not assembly:
        raise ValueError("assembly must not be empty")

    if not contig:
        raise ValueError("contig must not be empty")

    if not ref:
        raise ValueError("REF must not be empty")

    if not alt:
        raise ValueError("ALT must not be empty")

    if start < 0:
        raise ValueError(
            "start must be >= 0"
        )

    if end < start:
        raise ValueError(
            "end must be >= start"
        )

    return {
        "assembly": assembly,
        "contig": contig,
        "start": start,
        "end": end,
        "ref": ref,
        "alt": alt,
    }


def canonical_variant_payload(
    allele: Mapping[str, object],
) -> dict[str, object]:
    """
    Return the canonical content used for deterministic
    Phase 1B biological VARIANT identity.

    This function assumes the supplied coordinates/alleles
    are already the normalized values produced by the
    upstream frozen workflow. It does not perform reference
    normalization or haplotype equivalence.
    """

    validated = _validated_allele(
        allele
    )

    return {
        "identity_schema_version":
            IDENTITY_SCHEMA_VERSION,
        "assembly":
            validated["assembly"],
        "contig":
            validated["contig"],
        "normalized_start_0based":
            validated["start"],
        "normalized_end_0based":
            validated["end"],
        "normalized_ref":
            validated["ref"],
        "normalized_alt":
            validated["alt"],
    }


def variant_id(
    allele: Mapping[str, object],
) -> str:
    """
    Generate a deterministic content-derived VARIANT ID.
    """

    payload = canonical_variant_payload(
        allele
    )

    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    digest = hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()

    return f"variant:sha256:{digest}"


def normalized_identity_tuple(
    allele: Mapping[str, object],
) -> tuple[object, ...]:
    validated = _validated_allele(
        allele
    )

    return (
        validated["assembly"],
        validated["contig"],
        validated["start"],
        validated["end"],
        validated["ref"],
        validated["alt"],
    )


def classify_identity(
    allele_a: Mapping[str, object],
    allele_b: Mapping[str, object],
) -> str:
    """
    Conservative Phase 1B v1 identity classifier.

    Rules are intentionally narrow:

    1. Different assemblies are NON_EQUIVALENT.
    2. Different contigs are NON_EQUIVALENT.
    3. Exact equality across assembly, contig, normalized
       start/end, REF and ALT is EXACT_NORMALIZED_ALLELE.
    4. If normalized coordinates are identical but REF/ALT
       differ, records are NON_EQUIVALENT.
    5. All remaining representation differences are
       UNRESOLVED.

    REPRESENTATION_EQUIVALENCE_SUPPORTED is deliberately
    never emitted by v1 because no reference/haplotype
    equivalence procedure has yet been validated.
    """

    a = _validated_allele(
        allele_a
    )

    b = _validated_allele(
        allele_b
    )

    if a["assembly"] != b["assembly"]:
        return NON_EQUIVALENT

    if a["contig"] != b["contig"]:
        return NON_EQUIVALENT

    if normalized_identity_tuple(
        a
    ) == normalized_identity_tuple(
        b
    ):
        return EXACT_NORMALIZED_ALLELE

    same_normalized_span = (
        a["start"] == b["start"]
        and
        a["end"] == b["end"]
    )

    if same_normalized_span:
        return NON_EQUIVALENT

    return UNRESOLVED
