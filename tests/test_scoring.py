"""Tests for rubric invariants and score calculations."""

from collections.abc import Callable

import pytest

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import (
    AnalysisFinding,
    CheckId,
    CheckStatus,
    RepositorySnapshot,
)
from github_portfolio_reviewer.scoring import CHECK_SPECIFICATIONS, score_repository


def _findings_with_status(status: CheckStatus) -> tuple[AnalysisFinding, ...]:
    return tuple(
        AnalysisFinding(check_id, status, "test evidence") for check_id in CheckId
    )


def test_rubric_contains_every_check_and_totals_100() -> None:
    assert set(CHECK_SPECIFICATIONS) == set(CheckId)
    assert sum(spec.max_points for spec in CHECK_SPECIFICATIONS.values()) == 100


@pytest.mark.parametrize(
    ("status", "expected_score"),
    [
        (CheckStatus.PASS, 100.0),
        (CheckStatus.PARTIAL, 50.0),
        (CheckStatus.FAIL, 0.0),
    ],
)
def test_statuses_receive_full_half_or_zero_points(
    make_snapshot: Callable[..., RepositorySnapshot],
    status: CheckStatus,
    expected_score: float,
) -> None:
    report = score_repository(make_snapshot(), _findings_with_status(status))

    assert report.score == expected_score
    assert sum(score.points for score in report.category_scores) == report.score
    assert sum(score.max_points for score in report.category_scores) == 100


def test_score_rejects_missing_or_duplicate_findings(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = list(_findings_with_status(CheckStatus.PASS))
    findings[-1] = findings[0]

    with pytest.raises(ValueError, match="every analysis check"):
        score_repository(make_snapshot(), tuple(findings))


def test_real_empty_analysis_stays_within_score_bounds(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    snapshot = make_snapshot()
    report = score_repository(snapshot, analyze_repository(snapshot))

    assert 0 <= report.score <= 100
