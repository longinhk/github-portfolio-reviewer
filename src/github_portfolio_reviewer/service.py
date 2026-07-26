"""Application service that orchestrates repository review use cases."""

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
) -> ReviewReport:
    """Fetch, analyze, and score one public GitHub repository."""
    reference = parse_repository_reference(repository_input)
    github_client = client or GitHubClient(token=token)
    snapshot = github_client.fetch_repository(reference)
    findings = analyze_repository(snapshot)
    return score_repository(snapshot, findings)
