"""Application service that orchestrates repository review use cases."""

from collections.abc import Callable

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.github_client import (
    GitHubClient,
    parse_repository_reference,
)
from github_portfolio_reviewer.models import ReviewReport
from github_portfolio_reviewer.scoring import score_repository


def review_repository(
    repository_input: str,
    *,
    token: str | None = None,
    client: GitHubClient | None = None,
    progress: Callable[[str], None] | None = None,
) -> ReviewReport:
    """Fetch, analyze, and score one public GitHub repository.

    Args:
        repository_input: Public repository URL or ``owner/repository`` value.
        token: Optional GitHub token used by the API client.
        client: Optional client override used by offline tests.
        progress: Optional presentation callback for pipeline status updates.
    """
    reference = parse_repository_reference(repository_input)
    github_client = client or GitHubClient(token=token)
    _notify(progress, "Fetching repository metadata and file tree")
    snapshot = github_client.fetch_repository(reference)
    _notify(progress, "Inspecting README, structure, tests, CI, docs, and security")
    findings = analyze_repository(snapshot)
    _notify(progress, "Calculating the transparent 100-point score")
    return score_repository(snapshot, findings)


def _notify(progress: Callable[[str], None] | None, message: str) -> None:
    """Send a progress message when the caller supplied a callback."""
    if progress is not None:
        progress(message)
