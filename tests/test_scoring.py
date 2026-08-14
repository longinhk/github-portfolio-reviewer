"""Tests for rubric invariants and score calculations."""

from collections.abc import Callable

import pytest

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import (
    AnalysisFinding,
    Category,
    CheckId,
    CheckStatus,
    EvidenceConfidence,
    RepositorySnapshot,
    ReviewMode,
)
from github_portfolio_reviewer.scoring import (
    CHECK_SPECIFICATIONS,
    CHECK_TARGETS,
    RULESET_VERSION,
    score_band,
    score_repository,
)


def _findings_with_status(status: CheckStatus) -> tuple[AnalysisFinding, ...]:
    return tuple(
        AnalysisFinding(check_id, status, "test evidence") for check_id in CheckId
    )


def test_rubric_contains_every_check_and_totals_100() -> None:
    assert set(CHECK_SPECIFICATIONS) == set(CheckId)
    assert set(CHECK_TARGETS) == set(CheckId)
    assert sum(spec.max_points for spec in CHECK_SPECIFICATIONS.values()) == 100

    category_totals = {
        category: sum(
            specification.max_points
            for specification in CHECK_SPECIFICATIONS.values()
            if specification.category == category
        )
        for category in Category
    }
    assert category_totals == {
        Category.METADATA: 10,
        Category.README: 25,
        Category.STRUCTURE: 15,
        Category.TESTS: 15,
        Category.CI_CD: 10,
        Category.DOCUMENTATION: 10,
        Category.SECURITY: 15,
    }


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


def test_high_score_band_describes_presentation_not_job_readiness() -> None:
    assert score_band(100) == "Very strong presentation"


def test_report_records_ruleset_and_mode_without_changing_score(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = _findings_with_status(CheckStatus.PARTIAL)

    general = score_repository(make_snapshot(), findings)
    ai_ml = score_repository(make_snapshot(), findings, review_mode=ReviewMode.AI_ML)

    assert general.score == ai_ml.score == 50
    assert general.review_mode == ReviewMode.GENERAL
    assert ai_ml.review_mode == ReviewMode.AI_ML
    assert general.ruleset_version == ai_ml.ruleset_version == RULESET_VERSION
    assert RULESET_VERSION == "1.4.0"


def test_scoring_preserves_structured_sources_and_target(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = list(_findings_with_status(CheckStatus.PASS))
    index = list(CheckId).index(CheckId.TEST_QUALITY)
    findings[index] = AnalysisFinding(
        CheckId.TEST_QUALITY,
        CheckStatus.PASS,
        "Two implemented tests found.",
        ("tests/test_service.py",),
        EvidenceConfidence.SAMPLED,
    )

    report = score_repository(make_snapshot(), tuple(findings))
    check = next(
        item for item in report.checks if item.check_id == CheckId.TEST_QUALITY
    )

    assert check.sources == ("tests/test_service.py",)
    assert check.target == "Test implementation"
    assert check.confidence == EvidenceConfidence.SAMPLED
    assert report.score_is_provisional is True
    assert report.evidence_counts[EvidenceConfidence.SAMPLED] == 1


def test_fully_verified_report_is_not_provisional(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    report = score_repository(make_snapshot(), _findings_with_status(CheckStatus.PASS))

    assert report.score == 100
    assert report.score_is_provisional is False
