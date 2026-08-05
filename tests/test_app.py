"""Rendering and presentation-helper tests for the Streamlit app."""

from collections.abc import Callable
from pathlib import Path

from streamlit.testing.v1 import AppTest

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.app import (
    LINKED_SCOPE_LABEL,
    _check_counts,
    _check_rows_markup,
    _error_presentation,
    _filter_checks,
    _projected_score,
    _source_url,
    _updated_recent_repositories,
)
from github_portfolio_reviewer.github_client import (
    AuthenticationError,
    InvalidRepositoryError,
    RateLimitError,
    RepositoryNotFoundError,
)
from github_portfolio_reviewer.models import (
    Category,
    CheckId,
    CheckStatus,
    EvidenceConfidence,
    RepositoryReference,
    RepositorySnapshot,
    ReviewMode,
    ReviewReport,
    ScoredCheck,
    Suggestion,
    SuggestionKind,
)
from github_portfolio_reviewer.scoring import score_repository


def _make_check(
    check_id: CheckId,
    status: CheckStatus,
    category: Category,
    title: str,
    evidence: str,
    confidence: EvidenceConfidence = EvidenceConfidence.VERIFIED,
) -> ScoredCheck:
    points = 2.0 if status == CheckStatus.PASS else 1.0
    return ScoredCheck(
        check_id=check_id,
        category=category,
        title=title,
        status=status,
        evidence=evidence,
        points=points,
        max_points=2,
        recommendation="Improve this signal.",
        confidence=confidence,
    )


def test_initial_page_renders_without_exceptions() -> None:
    entry_point = Path(__file__).parents[1] / "streamlit_app.py"

    app = AppTest.from_file(str(entry_point)).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "Repository review"
    assert any(button.label == "Run review" for button in app.button)
    assert any(button.label == "Use example" for button in app.button)
    repository_input = next(
        text_input for text_input in app.text_input if text_input.label == "Repository"
    )
    assert "/tree/" in repository_input.help
    assert "default branch" in repository_input.help
    review_focus = next(
        selectbox for selectbox in app.selectbox if selectbox.label == "Review focus"
    )
    assert review_focus.value == ReviewMode.GENERAL.value
    review_scope = next(
        selectbox for selectbox in app.selectbox if selectbox.label == "Review scope"
    )
    assert review_scope.value == LINKED_SCOPE_LABEL
    assert "default-branch /tree/ URL" in review_scope.help
    assert any("No AI API" in caption.value for caption in app.caption)
    assert any(
        expander.label == "Scope, limitations & cost" for expander in app.expander
    )
    assert any(
        "REQUIRED COST" in markdown.value and "$0" in markdown.value
        for markdown in app.markdown
    )


def test_report_page_renders_all_sections_without_exceptions(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    entry_point = Path(__file__).parents[1] / "streamlit_app.py"
    snapshot = make_snapshot(
        description="A detailed repository description for the rendering test.",
        readme=(
            "# Example project\n\n"
            "## Installation\n\nInstall the project.\n\n"
            "## Usage\n\nRun the application.\n"
        ),
        files=("app.py", "tests/test_app.py", "pyproject.toml"),
        inspection_truncated=True,
    )
    report = score_repository(snapshot, analyze_repository(snapshot))
    app = AppTest.from_file(str(entry_point))
    app.session_state["review_report"] = report

    app.run(timeout=10)

    assert not app.exception
    assert any(button.label == "Run review" for button in app.button)
    assert [tab.label for tab in app.tabs] == [
        "Overview",
        f"Checks ({len(CheckId)})",
        "Recommendations",
    ]
    assert any("Portable reports" in caption.value for caption in app.caption)
    assert any(
        "Some eligible content could not be inspected" in info.value
        for info in app.info
    )
    assert any(
        "PORTFOLIO PRESENTATION SCORE" in markdown.value for markdown in app.markdown
    )
    assert any(
        expander.label == "Why this repository type?" for expander in app.expander
    )
    evidence_markup = next(
        markdown.value
        for markdown in app.markdown
        if '<section class="rubric-evidence"' in markdown.value
    )
    assert report.rubric_assessment.explanation in evidence_markup
    assert all(signal in evidence_markup for signal in report.rubric_assessment.signals)
    assert 'aria-label="Repository type classification evidence"' in evidence_markup
    assert any(
        expander.label == "Scope, limitations & cost" for expander in app.expander
    )


def test_scoped_report_identifies_the_linked_folder(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    entry_point = Path(__file__).parents[1] / "streamlit_app.py"
    snapshot = make_snapshot(
        html_url="https://github.com/example/project/tree/main/packages/api",
        files=("pyproject.toml", "api.py", "tests/test_api.py"),
        scope_path="packages/api",
    )
    report = score_repository(snapshot, analyze_repository(snapshot))
    app = AppTest.from_file(str(entry_point))
    app.session_state["review_report"] = report

    app.run(timeout=10)

    assert not app.exception
    assert any("Review scope: packages/api" in info.value for info in app.info)
    assert any(
        "SUBDIRECTORY" in markdown.value and "repo-label-scope" in markdown.value
        for markdown in app.markdown
    )
    assert any(
        "REVIEW SCOPE" in markdown.value and "packages/api" in markdown.value
        for markdown in app.markdown
    )


def test_check_rows_show_outcome_and_evidence_confidence(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    checks = (
        _make_check(
            CheckId.TEST_FILES,
            CheckStatus.FAIL,
            Category.TESTS,
            "Automated tests",
            "No test files were found.",
            EvidenceConfidence.VERIFIED,
        ),
        _make_check(
            CheckId.TEST_QUALITY,
            CheckStatus.PARTIAL,
            Category.TESTS,
            "Test implementation",
            "A bounded sample was inspected.",
            EvidenceConfidence.SAMPLED,
        ),
        _make_check(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.PARTIAL,
            Category.TESTS,
            "Test configuration",
            "Configuration could not be inspected.",
            EvidenceConfidence.UNVERIFIED,
        ),
        _make_check(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            Category.DOCUMENTATION,
            "Extended documentation",
            "The file tree was truncated.",
            EvidenceConfidence.PROVISIONAL,
        ),
    )
    report = ReviewReport(repository=make_snapshot(), checks=checks)

    markup = _check_rows_markup(checks, report)

    assert "NEEDS WORK" in markup
    assert ">MISSING<" not in markup
    for confidence in EvidenceConfidence:
        assert f"confidence-{confidence.value}" in markup
        assert f">{confidence.value.upper()}</span>" in markup


def test_check_counts_and_filters() -> None:
    checks = (
        _make_check(
            CheckId.DESCRIPTION,
            CheckStatus.PASS,
            Category.METADATA,
            "Description",
            "A description is present.",
        ),
        _make_check(
            CheckId.README_USAGE,
            CheckStatus.PARTIAL,
            Category.README,
            "Usage examples",
            "A short example exists.",
        ),
        _make_check(
            CheckId.TEST_FILES,
            CheckStatus.FAIL,
            Category.TESTS,
            "Automated tests",
            "No test files were found.",
        ),
    )

    assert _check_counts(checks) == {
        CheckStatus.PASS: 1,
        CheckStatus.PARTIAL: 1,
        CheckStatus.FAIL: 1,
    }
    assert (
        _filter_checks(
            checks,
            status_filter="Needs attention",
            category=None,
            search_query="",
        )
        == checks[1:]
    )
    assert _filter_checks(
        checks,
        status_filter="All",
        category=Category.TESTS,
        search_query="test files",
    ) == (checks[2],)


def test_projected_score_is_capped_at_100() -> None:
    suggestions = (
        Suggestion("High", Category.TESTS, "Tests", "Add tests.", 8),
        Suggestion("Medium", Category.README, "README", "Expand README.", 5),
    )

    assert _projected_score(72, suggestions) == 85
    assert _projected_score(96, suggestions) == 100


def test_manual_review_does_not_claim_recoverable_points() -> None:
    suggestions = (
        Suggestion(
            "Medium",
            Category.CI_CD,
            "Pinned actions",
            "Review remaining workflows.",
            4,
            kind=SuggestionKind.MANUAL_REVIEW,
        ),
    )

    assert _projected_score(80, suggestions) == 80


def test_low_fit_content_repository_is_rendered_without_numeric_score(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    entry_point = Path(__file__).parents[1] / "streamlit_app.py"
    snapshot = make_snapshot(
        reference=RepositoryReference("example", "learning-notes"),
        description="Lecture notes, slides, and learning resources",
        readme="# Learning notes",
        files=(
            "README.md",
            "notes/introduction.md",
            "notes/model.ipynb",
            "slides/week-1.pdf",
        ),
    )
    report = score_repository(snapshot, analyze_repository(snapshot))
    app = AppTest.from_file(str(entry_point))
    app.session_state["review_report"] = report

    app.run(timeout=10)

    assert not app.exception
    assert report.presentation_score is None
    assert any("rubric fit: Low" in warning.value for warning in app.warning)
    assert any(
        "score-value-unscored" in markdown.value and "NOT SCORED" in markdown.value
        for markdown in app.markdown
    )
    assert any("⚠ LOW RUBRIC FIT" in markdown.value for markdown in app.markdown)
    evidence_markup = next(
        markdown.value
        for markdown in app.markdown
        if '<section class="rubric-evidence"' in markdown.value
    )
    assert "Educational or content repository" in evidence_markup
    assert "Content-oriented repository" in evidence_markup
    assert "4 content file(s) and 0 test file(s)" in evidence_markup
    assert any(
        "Category scores are hidden" in markdown.value for markdown in app.markdown
    )


def test_recent_repositories_are_most_recent_unique_and_limited() -> None:
    current = ("one/repo", "two/repo", "three/repo", "four/repo")

    assert _updated_recent_repositories(current, "two/repo") == (
        "two/repo",
        "one/repo",
        "three/repo",
        "four/repo",
    )
    assert _updated_recent_repositories(current, "five/repo") == (
        "five/repo",
        "one/repo",
        "two/repo",
        "three/repo",
    )


def test_expected_errors_have_specific_presentations() -> None:
    errors = (
        InvalidRepositoryError("invalid"),
        RepositoryNotFoundError("missing"),
        AuthenticationError("token"),
        RateLimitError("limited"),
    )

    titles = {_error_presentation(error)[0] for error in errors}

    assert len(titles) == len(errors)


def test_source_url_encodes_branch_and_path(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    report = ReviewReport(
        repository=make_snapshot(default_branch="feature/review"),
        checks=(),
    )

    assert _source_url(report, "docs/review notes.md") == (
        "https://github.com/example/project/blob/"
        "feature%2Freview/docs/review%20notes.md"
    )
