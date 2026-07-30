"""Tests for deterministic, safe report exports."""

import json
from datetime import UTC, datetime

from github_portfolio_reviewer.models import (
    Category,
    CheckId,
    CheckStatus,
    RepositoryReference,
    RepositorySnapshot,
    RepositoryTextFile,
    ReviewMode,
    ReviewReport,
    ScoredCheck,
)
from github_portfolio_reviewer.reporting import (
    render_json_report,
    render_markdown_report,
    report_to_dict,
)


def _make_report() -> ReviewReport:
    snapshot = RepositorySnapshot(
        reference=RepositoryReference("example", "portfolio"),
        html_url="https://github.com/example/portfolio",
        description="A useful | portfolio\nreview project",
        default_branch="main",
        stars=12,
        forks=3,
        open_issues=2,
        language="Python",
        topics=("python", "developer-tools"),
        license_name="MIT License",
        archived=False,
        fork=False,
        created_at=datetime(2025, 1, 2, 3, 4, tzinfo=UTC),
        pushed_at=datetime(2026, 7, 29, 8, 30, tzinfo=UTC),
        readme="RAW-README-CONTENT-MUST-NOT-BE-EXPORTED",
        files=("RAW-FILE-TREE-MUST-NOT-BE-EXPORTED",),
        tree_truncated=False,
        inspected_files=(
            RepositoryTextFile(
                path="pyproject.toml",
                content="RAW-INSPECTED-CONTENT-MUST-NOT-BE-EXPORTED",
            ),
        ),
        inspection_truncated=False,
    )
    checks = (
        ScoredCheck(
            check_id=CheckId.DESCRIPTION,
            category=Category.METADATA,
            title="Clear repository description",
            status=CheckStatus.PASS,
            evidence="A clear description is present.",
            points=3,
            max_points=3,
            recommendation="Keep the description current.",
            sources=("GitHub metadata",),
            target="GitHub About section",
        ),
        ScoredCheck(
            check_id=CheckId.README_USAGE,
            category=Category.README,
            title="Usage examples",
            status=CheckStatus.PARTIAL,
            evidence="One command | no output\nAdd expected output.",
            points=2,
            max_points=4,
            recommendation="Add a copyable example | and its output.\nKeep it short.",
            sources=("README|draft.md", "docs/usage.md"),
            target="README.md | docs/usage.md",
        ),
    )
    return ReviewReport(
        repository=snapshot,
        checks=checks,
        review_mode=ReviewMode.PYTHON,
        ruleset_version="2.1.0",
    )


def test_json_report_has_stable_explicit_schema() -> None:
    report = _make_report()

    first = render_json_report(report)
    second = render_json_report(report)
    data = json.loads(first)

    assert first == second
    assert list(data) == [
        "schema_version",
        "ruleset_version",
        "review_mode",
        "repository",
        "score",
        "categories",
        "checks",
        "suggestions",
    ]
    assert data["ruleset_version"] == "2.1.0"
    assert data["review_mode"] == "Python internship"
    assert data["score"] == {
        "points": 5,
        "max_points": 100,
        "band": "Early stage",
    }
    assert data["repository"]["created_at"] == "2025-01-02T03:04:00+00:00"
    assert data["checks"][1]["sources"] == ["README|draft.md", "docs/usage.md"]
    assert data["checks"][1]["target"] == "README.md | docs/usage.md"
    assert data["suggestions"][0]["check_id"] == "readme_usage"


def test_exports_exclude_raw_repository_content_and_timestamps() -> None:
    report = _make_report()

    structured = report_to_dict(report)
    json_export = render_json_report(report)
    markdown_export = render_markdown_report(report)
    combined = json_export + markdown_export

    assert "readme" not in structured["repository"]
    assert "files" not in structured["repository"]
    assert "inspected_files" not in structured["repository"]
    assert "generated_at" not in structured
    assert "RAW-README-CONTENT-MUST-NOT-BE-EXPORTED" not in combined
    assert "RAW-FILE-TREE-MUST-NOT-BE-EXPORTED" not in combined
    assert "RAW-INSPECTED-CONTENT-MUST-NOT-BE-EXPORTED" not in combined


def test_markdown_report_contains_evidence_recommendations_and_no_ai_note() -> None:
    markdown = render_markdown_report(_make_report())

    assert "# Repository review: example/portfolio" in markdown
    assert "**5/100 — Early stage**" in markdown
    assert "deterministic ruleset 2.1.0" in markdown
    assert "**Python internship** focus" in markdown
    assert "One command \\| no output<br>Add expected output." in markdown
    assert "README\\|draft.md" in markdown
    assert "README.md \\| docs/usage.md" in markdown
    assert "Add a copyable example \\| and its output.<br>Keep it short." in markdown
    assert "`readme_usage`" in markdown
    assert "No AI API is required." in markdown


def test_markdown_table_rows_never_contain_unescaped_content_newlines() -> None:
    markdown = render_markdown_report(_make_report())
    check_row = next(line for line in markdown.splitlines() if "Usage examples" in line)

    assert "<br>" in check_row
    assert " | no output" not in check_row
    assert " | docs/usage.md" not in check_row
