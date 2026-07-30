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

    def fetch_repository(self, reference: RepositoryReference) -> RepositorySnapshot:
        self.reference = reference
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
    assert report.repository == client.snapshot
    assert len(report.checks) == len(CheckId)
    assert report.review_mode == ReviewMode.BACKEND
    assert 0 <= report.score <= 100
    assert progress_messages == [
        "1/3 Fetching repository evidence from GitHub",
        "2/3 Inspecting deterministic portfolio signals",
        "3/3 Calculating the portfolio presentation score",
    ]
