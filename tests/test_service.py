"""Offline integration tests for the review orchestration service."""

from collections.abc import Callable

from github_portfolio_reviewer.models import (
    CheckId,
    RepositoryReference,
    RepositorySnapshot,
    ReviewMode,
)
from github_portfolio_reviewer.service import review_repository


class FakeGitHubClient:
    """Return a known snapshot while recording the parsed reference."""

    def __init__(self, snapshot: RepositorySnapshot) -> None:
        self.snapshot = snapshot
        self.reference: RepositoryReference | None = None
        self.scope_to_linked_subdirectory = False

    def fetch_repository(
        self,
        reference: RepositoryReference,
        *,
        scope_to_linked_subdirectory: bool = False,
    ) -> RepositorySnapshot:
        self.reference = reference
        self.scope_to_linked_subdirectory = scope_to_linked_subdirectory
        return self.snapshot


def test_review_repository_runs_complete_pipeline_offline(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    client = FakeGitHubClient(make_snapshot(files=("app.py",)))
    progress_messages: list[str] = []

    report = review_repository(
        "example/project",
        client=client,  # type: ignore[arg-type]
        review_mode=ReviewMode.BACKEND,
        progress=progress_messages.append,
    )

    assert client.reference == RepositoryReference("example", "project")
    assert client.scope_to_linked_subdirectory is False
    assert report.repository == client.snapshot
    assert len(report.checks) == len(CheckId)
    assert report.review_mode == ReviewMode.BACKEND
    assert 0 <= report.score <= 100
    assert progress_messages == [
        "1/3 Fetching repository evidence from GitHub",
        "2/3 Inspecting deterministic portfolio signals",
        "3/3 Checking rubric fit and calculating the report",
    ]


def test_review_repository_can_opt_into_linked_subdirectory(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    client = FakeGitHubClient(make_snapshot(scope_path="packages/api"))

    report = review_repository(
        "https://github.com/example/project/tree/main/packages/api",
        client=client,  # type: ignore[arg-type]
        scope_to_linked_subdirectory=True,
    )

    assert client.reference == RepositoryReference(
        "example",
        "project",
        linked_tree_path=("main", "packages", "api"),
    )
    assert client.scope_to_linked_subdirectory is True
    assert report.repository.scope_path == "packages/api"
