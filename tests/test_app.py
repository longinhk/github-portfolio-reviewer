"""Rendering and presentation-helper tests for the Streamlit app."""

from collections.abc import Callable
from pathlib import Path

from streamlit.testing.v1 import AppTest

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.app import (
    _check_counts,
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
    RepositorySnapshot,
    ReviewMode,
    ReviewReport,
    ScoredCheck,
    Suggestion,
)
from github_portfolio_reviewer.scoring import score_repository


def _make_check(
    check_id: CheckId,
    status: CheckStatus,
    category: Category,
    title: str,
    evidence: str,
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
    )


def test_initial_page_renders_without_exceptions() -> None:
    entry_point = Path(__file__).parents[1] / "streamlit_app.py"

    app = AppTest.from_file(str(entry_point)).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "Repository review"
    assert any(button.label == "Run review" for button in app.button)
    assert any(button.label == "Use example" for button in app.button)
    review_focus = next(
        selectbox for selectbox in app.selectbox if selectbox.label == "Review focus"
    )
    assert review_focus.value == ReviewMode.GENERAL.value
    assert any("No AI API" in caption.value for caption in app.caption)


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
