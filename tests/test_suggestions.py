"""Tests for prioritized, deduplicated improvement suggestions."""

from collections.abc import Callable

from github_portfolio_reviewer.models import (
    AnalysisFinding,
    CheckId,
    CheckStatus,
    RepositorySnapshot,
)
from github_portfolio_reviewer.scoring import score_repository
from github_portfolio_reviewer.suggestions import generate_suggestions


def test_all_passing_checks_need_no_suggestions(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = tuple(
        AnalysisFinding(check_id, CheckStatus.PASS, "present") for check_id in CheckId
    )
    report = score_repository(make_snapshot(), findings)

    assert generate_suggestions(report) == ()


def test_parent_failures_suppress_dependent_suggestions(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = tuple(
        AnalysisFinding(check_id, CheckStatus.FAIL, "missing") for check_id in CheckId
    )
    report = score_repository(make_snapshot(), findings)

    suggestions = generate_suggestions(report, limit=None)
    titles = {suggestion.title for suggestion in suggestions}

    assert "README present" in titles
    assert "README gives sufficient context" not in titles
    assert "Installation instructions" not in titles
    assert "Automated tests" in titles
    assert "Coverage tracking" not in titles
    assert "CI workflow configuration" in titles
    assert "Visible CI status" not in titles


def test_suggestions_are_prioritized_and_limited(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = tuple(
        AnalysisFinding(check_id, CheckStatus.FAIL, "missing") for check_id in CheckId
    )
    report = score_repository(make_snapshot(), findings)

    suggestions = generate_suggestions(report, limit=3)

    assert len(suggestions) == 3
    assert all(suggestion.priority == "High" for suggestion in suggestions)
    assert suggestions[0].potential_points >= suggestions[1].potential_points
