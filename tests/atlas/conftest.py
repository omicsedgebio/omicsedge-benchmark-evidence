"""Pytest fixtures for the M0 Evidence Atlas protocol tests (SYNTHETIC data only)."""

from __future__ import annotations

import pytest

from atlas_synthetic import make_entities
from evidence_atlas import protocol


@pytest.fixture()
def entities() -> dict[str, dict]:
    return make_entities()


@pytest.fixture(scope="session")
def policy() -> dict:
    return protocol.load_config("eligibility_policy")


@pytest.fixture(scope="session")
def ml_policy() -> dict:
    return protocol.load_config("ml_policy")


@pytest.fixture()
def taxonomy() -> dict:
    return protocol.load_config("technology_taxonomy")


@pytest.fixture()
def organisms() -> dict:
    return protocol.load_config("organisms_assemblies")


@pytest.fixture()
def sources() -> dict:
    return protocol.load_config("sources")
