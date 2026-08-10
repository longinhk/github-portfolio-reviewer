"""Tests for deterministic, safe report exports."""

import json
from dataclasses import replace
from datetime import UTC, datetime

from github_portfolio_reviewer.models import (
    Category,
    CheckId,
    CheckStatus,
    EvidenceConfidence,
    RepositoryKind,
    RepositoryReference,
    RepositorySnapshot,
    RepositoryTextFile,
    ReviewMode,
    ReviewReport,
    RubricAssessment,
    RubricFit,
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
        commit_sha="a" * 40,
        readme_path="README.rst",
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
            confidence=EvidenceConfidence.SAMPLED,
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
        "review_scope",
        "rubric_assessment",
        "repository",
        "score",
        "categories",
        "checks",
        "suggestions",
    ]
    assert data["schema_version"] == "1.4"
    assert data["ruleset_version"] == "2.1.0"
    assert data["review_mode"] == "Python internship"
    assert data["score"] == {
        "kind": "portfolio_presentation",
        "points": 5,
        "max_points": 100,
        "band": "Early stage",
        "provisional": True,
        "evidence_counts": {
            "verified": 1,
            "sampled": 1,
            "unverified": 0,
            "provisional": 0,
        },
    }
    assert data["rubric_assessment"] == {
        "repository_type": "Unknown repository type",
        "fit": "Medium",
        "score_applicable": True,
        "explanation": "Repository type has not been classified.",
        "signals": [],
    }
    assert data["review_scope"] == {
        "public_repository_only": True,
        "default_branch_only": True,
        "bounded_inspection": True,
        "kind": "whole_repository",
        "path": None,
        "code_executed": False,
        "ai_api_used": False,
        "required_paid_services": False,
    }
    assert data["repository"]["created_at"] == "2025-01-02T03:04:00+00:00"
    assert data["repository"]["commit_sha"] == "a" * 40
    assert data["repository"]["readme_path"] == "README.rst"
    assert data["checks"][0]["confidence"] == "verified"
    assert data["checks"][1]["confidence"] == "sampled"
    assert data["checks"][1]["recommendation_kind"] == "Manual review"
    assert data["checks"][1]["sources"] == ["README|draft.md", "docs/usage.md"]
    assert data["checks"][1]["target"] == "README.md | docs/usage.md"
    assert data["suggestions"][0]["check_id"] == "readme_usage"
    assert data["suggestions"][0]["kind"] == "Manual review"


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

    assert "# Portfolio presentation review: example/portfolio" in markdown
    assert "## Portfolio presentation score" in markdown
    assert "**5/100 — Early stage**" in markdown
    assert "deterministic ruleset 2.1.0" in markdown
    assert "**Python internship** focus" in markdown
    assert "One command \\| no output<br>Add expected output." in markdown
    assert "README\\|draft.md" in markdown
    assert "README.md \\| docs/usage.md" in markdown
    assert "manual review" in markdown
    assert "`readme_usage`" in markdown
    assert "| PARTIAL | SAMPLED |" in markdown
    assert (
        "does not measure developer ability, code correctness, or security" in markdown
    )
    assert "Required paid services: $0" in markdown
    assert "No AI API is required." in markdown


def test_low_fit_report_withholds_numeric_score_and_recommendations() -> None:
    report = replace(
        _make_report(),
        rubric_assessment=RubricAssessment(
            repository_kind=RepositoryKind.CONTENT,
            fit=RubricFit.LOW,
            explanation="This is educational content.",
        ),
    )

    data = report_to_dict(report)
    markdown = render_markdown_report(report)

    assert data["score"] == {
        "kind": "portfolio_presentation",
        "points": None,
        "max_points": None,
        "band": "Not scored",
        "provisional": False,
        "evidence_counts": {
            "verified": 1,
            "sampled": 1,
            "unverified": 0,
            "provisional": 0,
        },
    }
    assert data["suggestions"] == []
    assert all(check["recommendation"] is None for check in data["checks"])
    assert "**Not scored" in markdown
    assert "Category scores are hidden" in markdown


def test_scoped_report_exports_the_selected_subdirectory() -> None:
    report = _make_report()
    scoped_report = replace(
        report,
        repository=replace(
            report.repository,
            html_url=("https://github.com/example/portfolio/tree/main/packages/api"),
            scope_path="packages/api",
        ),
    )

    data = report_to_dict(scoped_report)
    markdown = render_markdown_report(scoped_report)

    assert data["review_scope"]["kind"] == "subdirectory"
    assert data["review_scope"]["path"] == "packages/api"
    assert "| Review scope | packages/api |" in markdown
    assert "selected folder on a public repository's default branch" in markdown


def test_markdown_table_rows_never_contain_unescaped_content_newlines() -> None:
    markdown = render_markdown_report(_make_report())
    check_row = next(line for line in markdown.splitlines() if "Usage examples" in line)

    assert "<br>" in check_row
    assert " | no output" not in check_row
    assert " | docs/usage.md" not in check_row


def test_markdown_export_escapes_repository_controlled_html() -> None:
    report = _make_report()
    report = replace(
        report,
        repository=replace(
            report.repository,
            description='<img src=x onerror="alert(1)">',
        ),
    )

    markdown = render_markdown_report(report)

    assert "<img" not in markdown
    assert "&lt;img src=x onerror=" in markdown
