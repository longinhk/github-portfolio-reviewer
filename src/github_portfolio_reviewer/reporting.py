"""Deterministic Markdown and JSON exports for repository reviews."""

import json
from datetime import datetime
from typing import Any

from github_portfolio_reviewer.models import ReviewReport, Suggestion
from github_portfolio_reviewer.scoring import score_band
from github_portfolio_reviewer.suggestions import generate_suggestions

EXPORT_SCHEMA_VERSION = "1.1"


def report_to_dict(report: ReviewReport) -> dict[str, Any]:
    """Return a stable, explicitly allow-listed representation of a report.

    Raw README text, the complete file tree, inspected file contents, and
    credentials are intentionally outside the export schema.
    """
    repository = report.repository
    suggestions = generate_suggestions(report, limit=None)
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "ruleset_version": report.ruleset_version,
        "review_mode": report.review_mode.value,
        "review_scope": {
            "public_repository_only": True,
            "default_branch_only": True,
            "bounded_inspection": True,
            "code_executed": False,
            "ai_api_used": False,
            "required_paid_services": False,
        },
        "repository": {
            "full_name": repository.reference.full_name,
            "url": repository.html_url,
            "description": repository.description,
            "default_branch": repository.default_branch,
            "language": repository.language,
            "topics": list(repository.topics),
            "license": repository.license_name,
            "stars": repository.stars,
            "forks": repository.forks,
            "open_issues": repository.open_issues,
            "archived": repository.archived,
            "fork": repository.fork,
            "created_at": _isoformat(repository.created_at),
            "pushed_at": _isoformat(repository.pushed_at),
            "tree_truncated": repository.tree_truncated,
            "inspection_truncated": repository.inspection_truncated,
        },
        "score": {
            "kind": "portfolio_presentation",
            "points": report.score,
            "max_points": 100,
            "band": score_band(report.score),
        },
        "categories": [
            {
                "category": category_score.category.value,
                "points": category_score.points,
                "max_points": category_score.max_points,
            }
            for category_score in report.category_scores
        ],
        "checks": [
            {
                "id": check.check_id.value,
                "category": check.category.value,
                "title": check.title,
                "status": check.status.value,
                "confidence": check.confidence.value,
                "points": check.points,
                "max_points": check.max_points,
                "evidence": check.evidence,
                "sources": list(check.sources),
                "target": check.target,
                "recommendation": check.recommendation,
            }
            for check in report.checks
        ],
        "suggestions": [
            _suggestion_to_dict(report, suggestion) for suggestion in suggestions
        ],
    }


def render_json_report(report: ReviewReport) -> str:
    """Render a report as stable, human-readable JSON without a timestamp."""
    return json.dumps(
        report_to_dict(report),
        ensure_ascii=False,
        indent=2,
    )


def render_markdown_report(report: ReviewReport) -> str:
    """Render a report as a portable Markdown document."""
    data = report_to_dict(report)
    repository = data["repository"]
    score = data["score"]
    lines = [
        f"# Portfolio presentation review: {repository['full_name']}",
        "",
        (
            f"[{repository['full_name']}]({repository['url']}) was reviewed with "
            f"deterministic ruleset {data['ruleset_version']} using the "
            f"**{data['review_mode']}** focus."
        ),
        "",
        "## Portfolio presentation score",
        "",
        f"**{_format_points(score['points'])}/{score['max_points']} — {score['band']}**",
        "",
        "## Repository facts",
        "",
        "| Fact | Value |",
        "| --- | --- |",
        _table_row("Description", repository["description"] or "Not provided"),
        _table_row("Default branch", repository["default_branch"]),
        _table_row("Language", repository["language"] or "Unknown"),
        _table_row("Topics", ", ".join(repository["topics"]) or "None"),
        _table_row("License", repository["license"] or "Not detected"),
        _table_row("Stars", repository["stars"]),
        _table_row("Forks", repository["forks"]),
        _table_row("Open issues", repository["open_issues"]),
        _table_row("Created", repository["created_at"] or "Unknown"),
        _table_row("Last pushed", repository["pushed_at"] or "Unknown"),
        _table_row("Archived", _yes_no(repository["archived"])),
        _table_row("Fork", _yes_no(repository["fork"])),
        "",
        "## Category breakdown",
        "",
        "| Category | Points |",
        "| --- | ---: |",
    ]
    lines.extend(
        _table_row(
            category["category"],
            f"{_format_points(category['points'])}/{category['max_points']}",
        )
        for category in data["categories"]
    )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            (
                "| Status | Confidence | Category | Check | Points | Evidence | "
                "Sources | Target | Recommendation |"
            ),
            "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        _table_row(
            check["status"].upper(),
            check["confidence"].upper(),
            check["category"],
            check["title"],
            f"{_format_points(check['points'])}/{check['max_points']}",
            check["evidence"],
            ", ".join(check["sources"]) or "None",
            check["target"],
            check["recommendation"],
        )
        for check in data["checks"]
    )
    lines.extend(["", "## Recommendations", ""])
    if data["suggestions"]:
        for index, suggestion in enumerate(data["suggestions"], start=1):
            check_reference = (
                f" · `{suggestion['check_id']}`" if suggestion["check_id"] else ""
            )
            lines.extend(
                [
                    (
                        f"{index}. **{_markdown_text(suggestion['title'])}** "
                        f"({_markdown_text(suggestion['priority'])}, "
                        f"+{_format_points(suggestion['potential_points'])} points"
                        f"{check_reference})"
                    ),
                    f"   {_markdown_text(suggestion['action'])}",
                ]
            )
    else:
        lines.append("No open recommendations in this ruleset.")
    lines.extend(
        [
            "",
            "## Interpretation and limitations",
            "",
            (
                "This score measures visible portfolio and engineering signals. It "
                "does not measure developer ability, code correctness, or security."
            ),
            "",
            "- Only a public repository's default branch is reviewed.",
            "- Repository code, tests, and workflows are never executed.",
            (
                "- Content inspection is bounded, so sampled, unverified, and "
                "provisional evidence may require manual review."
            ),
            (
                "- This is not a complete code review, dependency audit, secret scan, "
                "or hiring decision."
            ),
            "",
            "**Required paid services: $0.** No AI API is required.",
            "",
            "---",
            "",
            (
                "Generated by GitHub Portfolio Reviewer using deterministic Python "
                "rules. No AI API is required."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _suggestion_to_dict(report: ReviewReport, suggestion: Suggestion) -> dict[str, Any]:
    check_id = suggestion.check_id
    if check_id is None:
        check_id = next(
            (
                check.check_id
                for check in report.checks
                if check.title == suggestion.title
                and check.category == suggestion.category
            ),
            None,
        )
    return {
        "check_id": check_id.value if check_id is not None else None,
        "priority": suggestion.priority,
        "category": suggestion.category.value,
        "title": suggestion.title,
        "action": suggestion.action,
        "potential_points": suggestion.potential_points,
    }


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _format_points(value: object) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f"{value:g}"
    return str(value)


def _yes_no(value: object) -> str:
    return "Yes" if value is True else "No"


def _table_row(*values: object) -> str:
    return "| " + " | ".join(_markdown_cell(value) for value in values) + " |"


def _markdown_cell(value: object) -> str:
    return _markdown_text(value).replace("|", r"\|")


def _markdown_text(value: object) -> str:
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
