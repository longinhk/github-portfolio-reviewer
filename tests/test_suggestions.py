"""Tests for prioritized, deduplicated improvement suggestions."""

from collections.abc import Callable

from github_portfolio_reviewer.models import (
    AnalysisFinding,
    CheckId,
    CheckStatus,
    EvidenceConfidence,
    RepositoryReference,
    RepositorySnapshot,
    ReviewMode,
    SuggestionKind,
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
    assert "Implemented test behavior" not in titles
    assert "Coverage tracking" not in titles
    assert "CI workflow configuration" in titles
    assert "Pinned GitHub Actions" not in titles
    assert "Least-privilege workflow permissions" not in titles
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


def test_review_mode_reorders_relevant_suggestions_without_changing_score(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = [
        AnalysisFinding(check_id, CheckStatus.PASS, "present") for check_id in CheckId
    ]
    for check_id in (CheckId.README_EXISTS, CheckId.NO_DETECTED_SECRETS):
        index = list(CheckId).index(check_id)
        findings[index] = AnalysisFinding(check_id, CheckStatus.FAIL, "missing")

    general_report = score_repository(
        make_snapshot(), tuple(findings), review_mode=ReviewMode.GENERAL
    )
    backend_report = score_repository(
        make_snapshot(), tuple(findings), review_mode=ReviewMode.BACKEND
    )
    general = generate_suggestions(general_report, limit=None)
    backend = generate_suggestions(backend_report, limit=None)

    assert general_report.score == backend_report.score
    assert general[0].check_id == CheckId.README_EXISTS
    assert backend[0].check_id == CheckId.NO_DETECTED_SECRETS
    assert {suggestion.check_id for suggestion in backend} == {
        CheckId.README_EXISTS,
        CheckId.NO_DETECTED_SECRETS,
    }


def test_incomplete_evidence_creates_manual_review_not_change_suggestions(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = [
        AnalysisFinding(check_id, CheckStatus.PASS, "present") for check_id in CheckId
    ]
    for check_id, confidence in (
        (CheckId.TOPICS, EvidenceConfidence.UNVERIFIED),
        (CheckId.LOCK_FILE, EvidenceConfidence.PROVISIONAL),
    ):
        index = list(CheckId).index(check_id)
        findings[index] = AnalysisFinding(
            check_id,
            CheckStatus.PARTIAL,
            "Evidence could not be confirmed.",
            confidence=confidence,
        )

    report = score_repository(make_snapshot(), tuple(findings))
    suggestions = generate_suggestions(report, limit=None)

    assert report.score < 100
    assert {suggestion.check_id for suggestion in suggestions} == {
        CheckId.TOPICS,
        CheckId.LOCK_FILE,
    }
    assert all(
        suggestion.kind == SuggestionKind.MANUAL_REVIEW for suggestion in suggestions
    )
    assert all(suggestion.potential_points == 0 for suggestion in suggestions)


def test_low_fit_repository_suppresses_software_project_suggestions(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = tuple(
        AnalysisFinding(check_id, CheckStatus.FAIL, "missing") for check_id in CheckId
    )
    snapshot = make_snapshot(
        reference=RepositoryReference("example", "learning-notes"),
        description="Lecture notes, slides, and learning resources",
        files=(
            "README.md",
            "notes/intro.md",
            "notes/model.ipynb",
            "slides/week-1.pdf",
        ),
    )
    report = score_repository(snapshot, findings)

    assert report.presentation_score is None
    assert generate_suggestions(report, limit=None) == ()


def test_sampled_workflow_result_requests_verification_without_points(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = [
        AnalysisFinding(check_id, CheckStatus.PASS, "present") for check_id in CheckId
    ]
    index = list(CheckId).index(CheckId.ACTIONS_PINNED)
    findings[index] = AnalysisFinding(
        CheckId.ACTIONS_PINNED,
        CheckStatus.PARTIAL,
        "Inspected workflows are pinned; additional workflows were not inspected.",
        confidence=EvidenceConfidence.SAMPLED,
    )
    report = score_repository(make_snapshot(), tuple(findings))

    suggestion = next(
        item
        for item in generate_suggestions(report, limit=None)
        if item.check_id == CheckId.ACTIONS_PINNED
    )

    assert suggestion.kind == SuggestionKind.MANUAL_REVIEW
    assert suggestion.potential_points == 0
    assert "remaining workflow files" in suggestion.action
    assert "do not change" in suggestion.action
