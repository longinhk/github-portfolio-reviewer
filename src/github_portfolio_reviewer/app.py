"""Streamlit interface for the GitHub Portfolio Reviewer."""

from datetime import datetime

import streamlit as st

from github_portfolio_reviewer.github_client import GitHubClientError
from github_portfolio_reviewer.models import (
    Category,
    CheckStatus,
    ReviewReport,
    Suggestion,
)
from github_portfolio_reviewer.scoring import score_band
from github_portfolio_reviewer.service import review_repository
from github_portfolio_reviewer.suggestions import generate_suggestions

STATUS_ICONS = {
    CheckStatus.PASS: "✅",
    CheckStatus.PARTIAL: "🟡",
    CheckStatus.FAIL: "❌",
}
PRIORITY_ICONS = {"High": "🔴", "Medium": "🟠", "Low": "🔵"}


def main() -> None:
    """Render the repository-review application."""
    st.set_page_config(
        page_title="GitHub Portfolio Reviewer",
        page_icon="🔍",
        layout="wide",
    )
    _render_introduction()
    token = _render_token_input()

    with st.form("repository-review-form"):
        repository_input = st.text_input(
            "Public GitHub repository",
            placeholder="owner/repository or https://github.com/owner/repository",
            help="Use the repository root, not a branch, issue, or file URL.",
        )
        submitted = st.form_submit_button(
            "Analyze repository", type="primary", use_container_width=True
        )

    if submitted:
        _run_review(repository_input, token)

    report = st.session_state.get("review_report")
    if isinstance(report, ReviewReport):
        _render_report(report)


def _render_introduction() -> None:
    st.title("GitHub Portfolio Reviewer")
    st.write(
        "Review how clearly a public repository presents your engineering work to "
        "internship recruiters and technical reviewers."
    )
    st.caption(
        "The score is a deterministic portfolio-presentation heuristic—not a measure "
        "of developer ability, code correctness, or a security audit."
    )


def _render_token_input() -> str | None:
    with st.sidebar:
        st.header("GitHub access")
        token = st.text_input(
            "Personal access token (optional)",
            type="password",
            help=(
                "A token raises GitHub API limits. Public-repository metadata needs "
                "no special scopes. The token is not included in the report."
            ),
        )
        configured_token = _secret_token()
        if configured_token and not token:
            st.success("Using the token configured in Streamlit secrets.")
        else:
            st.caption("Without a token, GitHub normally allows 60 API requests/hour.")
        st.divider()
        st.write(
            "Each review checks metadata, README, structure, tests, CI, docs, and security signals."
        )
    return token.strip() or configured_token


def _secret_token() -> str | None:
    try:
        value = st.secrets.get("GITHUB_TOKEN")
    except (FileNotFoundError, KeyError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _run_review(repository_input: str, token: str | None) -> None:
    st.session_state.pop("review_report", None)
    try:
        with st.spinner("Collecting repository evidence from GitHub…"):
            report = review_repository(repository_input, token=token)
    except GitHubClientError as error:
        st.error(str(error))
        return
    st.session_state["review_report"] = report


def _render_report(report: ReviewReport) -> None:
    repository = report.repository
    st.divider()
    st.subheader(repository.reference.full_name)
    st.link_button("Open repository on GitHub", repository.html_url)

    if repository.tree_truncated:
        st.warning(
            "GitHub truncated this very large repository's file tree. The score is "
            "provisional, and absent file-based checks receive partial credit."
        )

    score_column, language_column, stars_column, forks_column = st.columns(4)
    score_column.metric("Repository score", f"{_format_points(report.score)} / 100")
    language_column.metric("Primary language", repository.language or "Unknown")
    stars_column.metric("Stars", repository.stars)
    forks_column.metric("Forks", repository.forks)

    st.progress(report.score / 100, text=score_band(report.score))
    if repository.description:
        st.write(repository.description)

    overview_tab, checks_tab, suggestions_tab, metadata_tab = st.tabs(
        ["Score breakdown", "All checks", "Action plan", "Metadata"]
    )
    with overview_tab:
        _render_category_scores(report)
    with checks_tab:
        _render_checks(report)
    with suggestions_tab:
        _render_suggestions(report)
    with metadata_tab:
        _render_metadata(report)


def _render_category_scores(report: ReviewReport) -> None:
    for category_score in report.category_scores:
        label = (
            f"{category_score.category}: {_format_points(category_score.points)}"
            f"/{category_score.max_points}"
        )
        st.progress(
            category_score.points / category_score.max_points,
            text=label,
        )


def _render_checks(report: ReviewReport) -> None:
    for category in Category:
        checks = [check for check in report.checks if check.category == category]
        earned = sum(check.points for check in checks)
        available = sum(check.max_points for check in checks)
        with st.expander(
            f"{category} — {_format_points(earned)}/{available}",
            expanded=category in {Category.README, Category.TESTS},
        ):
            for check in checks:
                icon = STATUS_ICONS[check.status]
                st.markdown(
                    f"{icon} **{check.title}** — "
                    f"{_format_points(check.points)}/{check.max_points}"
                )
                st.caption(check.evidence)


def _render_suggestions(report: ReviewReport) -> None:
    suggestions = generate_suggestions(report, limit=None)
    if not suggestions:
        st.success(
            "Every current rubric check passed. Revisit the project as it evolves."
        )
        return

    st.write("Start with the highest-impact actions. Potential points are approximate.")
    for suggestion in suggestions[:8]:
        _render_suggestion(suggestion)
    if len(suggestions) > 8:
        with st.expander(f"Show {len(suggestions) - 8} additional suggestions"):
            for suggestion in suggestions[8:]:
                _render_suggestion(suggestion)


def _render_suggestion(suggestion: Suggestion) -> None:
    icon = PRIORITY_ICONS[suggestion.priority]
    st.markdown(f"{icon} **{suggestion.title}** · {suggestion.category}")
    st.write(suggestion.action)
    st.caption(f"Potential gain: {_format_points(suggestion.potential_points)} points")


def _render_metadata(report: ReviewReport) -> None:
    repository = report.repository
    metadata = {
        "Repository": repository.reference.full_name,
        "Default branch": repository.default_branch,
        "Primary language": repository.language or "Not detected",
        "Topics": ", ".join(repository.topics) if repository.topics else "None",
        "License": repository.license_name or "Not detected",
        "Open issues": repository.open_issues,
        "Fork": "Yes" if repository.fork else "No",
        "Archived": "Yes" if repository.archived else "No",
        "Created": _format_date(repository.created_at),
        "Last push": _format_date(repository.pushed_at),
        "Files inspected": len(repository.files),
    }
    for label, value in metadata.items():
        st.markdown(f"**{label}:** {value}")


def _format_date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "Unknown"


def _format_points(value: float) -> str:
    return f"{value:g}"


if __name__ == "__main__":
    main()
