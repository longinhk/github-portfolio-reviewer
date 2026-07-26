"""Shared offline fixtures for the test suite."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
import requests

from github_portfolio_reviewer.models import RepositoryReference, RepositorySnapshot


@pytest.fixture(autouse=True)
def prevent_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a test accidentally attempts a real HTTP request."""

    def blocked_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("Tests must not make real network requests.")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked_request)


@pytest.fixture
def make_snapshot() -> Callable[..., RepositorySnapshot]:
    """Return a factory for concise repository snapshots in unit tests."""

    def factory(**overrides: object) -> RepositorySnapshot:
        values: dict[str, object] = {
            "reference": RepositoryReference("example", "project"),
            "html_url": "https://github.com/example/project",
            "description": None,
            "default_branch": "main",
            "stars": 0,
            "forks": 0,
            "open_issues": 0,
            "language": "Python",
            "topics": (),
            "license_name": None,
            "archived": False,
            "fork": False,
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
            "pushed_at": datetime(2026, 1, 1, tzinfo=UTC),
            "readme": None,
            "files": (),
            "tree_truncated": False,
        }
        values.update(overrides)
        return RepositorySnapshot(**values)  # type: ignore[arg-type]

    return factory
