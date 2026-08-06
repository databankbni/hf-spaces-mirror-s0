from __future__ import annotations

import pytest

from underdog_lab.data.repository import MatchRepository


@pytest.fixture(scope="session")
def repository() -> MatchRepository:
    return MatchRepository()


@pytest.fixture()
def neutral_match(repository):
    return next(match for match in repository.list() if match.neutral_venue)


@pytest.fixture()
def home_match(repository):
    return next(match for match in repository.list() if not match.neutral_venue)
