"""Streamlit interface for the GitHub Portfolio Reviewer."""

import hashlib
from collections.abc import Sequence
from datetime import datetime
from html import escape
from urllib.parse import quote

import streamlit as st

from github_portfolio_reviewer.github_client import (
    AuthenticationError,
    GitHubAPIError,
    GitHubClient,
    GitHubClientError,
    InvalidRepositoryError,
    RateLimitError,
    RepositoryNotFoundError,
)
from github_portfolio_reviewer.models import (
    Category,
    CheckId,
    CheckStatus,
    ReviewMode,
    ReviewReport,
    ScoredCheck,
    Suggestion,
)
from github_portfolio_reviewer.reporting import (
    render_json_report,
    render_markdown_report,
)
from github_portfolio_reviewer.scoring import score_band
from github_portfolio_reviewer.service import review_repository
from github_portfolio_reviewer.styles import github_native_css
from github_portfolio_reviewer.suggestions import generate_suggestions

EXAMPLE_REPOSITORY = "longinhk/github-portfolio-reviewer"
RECENT_REPOSITORY_LIMIT = 4

STATUS_LABELS = {
    CheckStatus.PASS: "PASS",
    CheckStatus.PARTIAL: "PARTIAL",
    CheckStatus.FAIL: "MISSING",
}

CATEGORY_IMPACT = {
    Category.METADATA: "Helps recruiters understand and discover the project quickly.",
    Category.README: "Makes the project easier to evaluate, install, and demonstrate.",
    Category.STRUCTURE: "Shows that the codebase is maintainable and professionally organized.",
    Category.TESTS: "Provides evidence that important behavior is reliable.",
    Category.CI_CD: "Demonstrates an automated and repeatable engineering workflow.",
    Category.DOCUMENTATION: "Makes technical decisions and collaboration expectations clear.",
    Category.SECURITY: "Shows responsible handling of dependencies and sensitive information.",
}


def main() -> None:
    """Render the repository-review application."""
    st.set_page_config(
        page_title="Repository review",
        page_icon="⌘",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.session_state.setdefault("theme_mode", "Dark")
    st.markdown(
        github_native_css(_selected_theme()),
        unsafe_allow_html=True,
    )

    existing_report = st.session_state.get("review_report")
    has_report = isinstance(existing_report, ReviewReport)
    token = _render_product_bar()
    if not has_report:
        _render_introduction()
    repository_input, review_mode, submitted = _render_review_form(compact=has_report)
    _render_repository_shortcuts(compact=has_report)

    if submitted and _run_review(repository_input, token, review_mode):
        st.rerun()

    report = st.session_state.get("review_report")
    if isinstance(report, ReviewReport):
        _render_report(report)
    else:
        _render_empty_workspace()


def _selected_theme() -> str:
    """Return a supported appearance value from session state."""
    value = st.session_state.get("theme_mode", "Dark")
    return value if value in {"Dark", "Light"} else "Dark"


def _render_product_bar() -> str | None:
    brand_column, mode_column, settings_column = st.columns(
        [5, 1.35, 1.2], vertical_alignment="center"
    )
    with settings_column:
        with st.popover("Settings", use_container_width=True):
            st.markdown("#### Configuration")
            st.radio(
                "Appearance",
                ["Dark", "Light"],
                horizontal=True,
                key="theme_mode",
            )
            token = st.text_input(
                "GitHub token",
                type="password",
                key="github_token",
                help=(
                    "Optional. A token raises GitHub API limits. Public-repository "
                    "metadata needs no special scopes."
                ),
            )
            st.caption("Used only for GitHub requests and never included in reports.")

    configured_token = _secret_token()
    effective_token = token.strip() or configured_token
    api_mode = "AUTHENTICATED" if effective_token else "PUBLIC API"

    with brand_column:
        st.markdown(
            '<div class="product-brand">'
            '<span class="product-mark">&lt;/&gt;</span>'
            "<span><strong>repo-review</strong>"
            "<small>GitHub portfolio signal inspector</small></span>"
            "</div>",
            unsafe_allow_html=True,
        )
    with mode_column:
        st.markdown(
            f'<div class="api-mode"><span></span>{api_mode}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="product-divider"></div>', unsafe_allow_html=True)
    return effective_token


def _render_introduction() -> None:
    st.markdown(
        '<div class="app-kicker">GITHUB PORTFOLIO REVIEW</div>',
        unsafe_allow_html=True,
    )
    st.title("Repository review")
    st.caption(
        "See the engineering signals a recruiter can verify—and the highest-impact "
        "changes to make next."
    )
    st.caption(
        "Deterministic Python rules only. No AI API, model key, or paid inference "
        "service is required."
    )


def _render_review_form(*, compact: bool) -> tuple[str, ReviewMode, bool]:
    with st.form("repository-review-form", border=True):
        heading = (
            "Review another repository" if compact else "Review a public repository"
        )
        st.markdown(
            f'<div class="form-heading">{heading}</div>',
            unsafe_allow_html=True,
        )
        input_column, focus_column, button_column = st.columns(
            [4.1, 2, 1.35], vertical_alignment="bottom"
        )
        with input_column:
            repository_input = st.text_input(
                "Repository",
                placeholder="owner/repository or https://github.com/owner/repository",
                key="repository_input",
                help="Enter owner/repository or a public GitHub repository URL.",
            )
        with focus_column:
            review_mode_label = st.selectbox(
                "Review focus",
                [mode.value for mode in ReviewMode],
                key="review_mode",
                help=(
                    "Changes recommendation order only. The deterministic 100-point "
                    "rubric stays comparable across every focus."
                ),
            )
        with button_column:
            submitted = st.form_submit_button(
                "Run review", type="primary", use_container_width=True
            )
        st.markdown(
            '<div class="scope-line">'
            f"<span>{len(CheckId)} deterministic checks</span>"
            "<span>Read-only GitHub access</span>"
            "<span>No AI API or model key</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    return repository_input, ReviewMode(review_mode_label), submitted


def _render_repository_shortcuts(*, compact: bool) -> None:
    recent = _recent_repositories()
    labels = [("Use example", EXAMPLE_REPOSITORY)]
    labels.extend((repository, repository) for repository in recent)

    if compact:
        with st.expander("Repository shortcuts", expanded=False):
            _render_shortcut_buttons(labels)
            st.caption("Recent repositories are kept only for this browser session.")
        return

    _render_shortcut_buttons(labels)
    if recent:
        st.caption("Recent repositories are kept only for this browser session.")


def _render_shortcut_buttons(labels: Sequence[tuple[str, str]]) -> None:
    """Render buttons that fill the repository input without submitting it."""
    columns = st.columns([1.1] * len(labels) + [max(1.0, 5 - len(labels))])
    for index, (label, repository) in enumerate(labels):
        with columns[index]:
            st.button(
                label,
                key=f"repository-shortcut-{index}-{repository}",
                help=f"Fill the repository field with {repository}",
                on_click=_select_repository,
                args=(repository,),
                use_container_width=True,
            )


def _select_repository(repository: str) -> None:
    """Fill the repository input from an example or recent shortcut."""
    st.session_state["repository_input"] = repository


def _secret_token() -> str | None:
    try:
        value = st.secrets.get("GITHUB_TOKEN")
    except (FileNotFoundError, KeyError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _run_review(
    repository_input: str,
    token: str | None,
    review_mode: ReviewMode,
) -> bool:
    """Run a review and return whether a new report was stored."""
    if not repository_input.strip():
        st.error(
            "**Repository address is required**\n\n"
            "Enter owner/repository or a public GitHub repository URL."
        )
        return False

    has_previous_report = isinstance(
        st.session_state.get("review_report"), ReviewReport
    )
    status = st.status("Starting repository review…", expanded=True)
    try:
        report = review_repository(
            repository_input,
            client=_review_client(token),
            review_mode=review_mode,
            progress=status.write,
        )
    except GitHubClientError as error:
        title, guidance = _error_presentation(error)
        if has_previous_report:
            guidance += " Your previous successful report remains displayed below."
        status.update(label="Review failed", state="error", expanded=False)
        st.error(f"**{title}**\n\n{error}\n\n{guidance}")
        return False

    status.update(label="Review complete", state="complete", expanded=False)
    st.session_state["review_report"] = report
    _remember_repository(report.repository.reference.full_name)
    return True


def _review_client(token: str | None) -> GitHubClient:
    """Reuse one session-local client so its bounded response cache is effective."""
    normalized = token.strip() if token else ""
    fingerprint = (
        hashlib.sha256(normalized.encode()).hexdigest() if normalized else "public"
    )
    existing = st.session_state.get("_github_client")
    if (
        not isinstance(existing, GitHubClient)
        or st.session_state.get("_github_client_fingerprint") != fingerprint
    ):
        existing = GitHubClient(token=normalized or None)
        st.session_state["_github_client"] = existing
        st.session_state["_github_client_fingerprint"] = fingerprint
    return existing


def _error_presentation(error: GitHubClientError) -> tuple[str, str]:
    """Return a specific error title and next step for an expected failure."""
    if isinstance(error, InvalidRepositoryError):
        return (
            "Repository address is not valid",
            "Use owner/repository or the repository's root GitHub URL.",
        )
    if isinstance(error, RepositoryNotFoundError):
        return (
            "Repository is unavailable",
            "Confirm the spelling and make sure the repository is public.",
        )
    if isinstance(error, AuthenticationError):
        return (
            "GitHub token was rejected",
            "Open Settings, remove the token, or replace it with a valid token.",
        )
    if isinstance(error, RateLimitError):
        return (
            "GitHub API limit reached",
            "Add a token in Settings or wait until GitHub resets the request limit.",
        )
    if isinstance(error, GitHubAPIError):
        return (
            "GitHub could not complete the request",
            "Check your connection and try again. The repository was not changed.",
        )
    return "Review could not be completed", "Check the repository and try again."


def _render_empty_workspace() -> None:
    st.markdown(
        '<div class="empty-workspace">'
        '<div class="empty-copy">'
        '<h2 class="section-heading">WHAT THE REVIEW COVERS</h2>'
        "<h3>One report, seven engineering areas</h3>"
        "<p>The reviewer uses the GitHub REST API and deterministic Python rules. "
        "It inspects a bounded set of text files, but never clones, executes, or "
        "modifies the repository—and it never calls an AI service.</p>"
        '<div class="scope-pills">'
        "<span>Metadata</span><span>README</span><span>Structure</span>"
        "<span>Tests</span><span>CI/CD</span><span>Documentation</span>"
        "<span>Security</span>"
        "</div></div>"
        '<div class="workflow-list">'
        "<div><span>01</span><strong>Fetch</strong><small>Public GitHub signals</small></div>"
        f"<div><span>02</span><strong>Inspect</strong><small>{len(CheckId)} explicit checks</small></div>"
        "<div><span>03</span><strong>Improve</strong><small>Prioritized next actions</small></div>"
        "</div></div>",
        unsafe_allow_html=True,
    )


def _render_report(report: ReviewReport) -> None:
    repository = report.repository
    suggestions = generate_suggestions(report, limit=None)
    st.markdown('<div class="report-divider"></div>', unsafe_allow_html=True)

    heading_column, link_column = st.columns([5, 1], vertical_alignment="center")
    with heading_column:
        labels = ['<span class="repo-label">PUBLIC</span>']
        if repository.fork:
            labels.append('<span class="repo-label repo-label-muted">FORK</span>')
        if repository.archived:
            labels.append('<span class="repo-label repo-label-muted">ARCHIVED</span>')
        st.markdown(
            '<div class="repository-heading">'
            f'<a class="repo-path" href="{escape(repository.html_url)}" '
            'target="_blank" rel="noopener noreferrer">'
            f"{escape(repository.reference.full_name)}</a>"
            f'<span class="repo-labels">{"".join(labels)}</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with link_column:
        st.link_button(
            "View on GitHub",
            repository.html_url,
            use_container_width=True,
        )

    if repository.description:
        st.markdown(
            f'<p class="repo-description">{escape(repository.description)}</p>',
            unsafe_allow_html=True,
        )

    if repository.tree_truncated:
        st.warning(
            "GitHub returned a truncated file tree. Missing file-based signals receive "
            "partial credit, so this score is provisional."
        )
    if repository.inspection_truncated:
        st.info(
            "The bounded content-inspection limit was reached. Findings describe the "
            "sampled evidence and do not claim a full-repository code scan."
        )

    _render_score_summary(report)
    _render_repository_facts(report)
    _render_downloads(report)

    overview_tab, checks_tab, suggestions_tab = st.tabs(
        ["Overview", f"Checks ({len(report.checks)})", "Recommendations"]
    )
    with overview_tab:
        action_column, category_column = st.columns([1.05, 1], gap="large")
        with action_column:
            _render_top_actions(report, suggestions)
        with category_column:
            _render_category_scores(report)
    with checks_tab:
        _render_checks(report)
    with suggestions_tab:
        _render_suggestions(report, suggestions)


def _render_score_summary(report: ReviewReport) -> None:
    counts = _check_counts(report.checks)
    score = _format_points(report.score)
    available = _format_points(100 - report.score)
    percentage = round(report.score)
    st.markdown(
        '<div class="summary-grid">'
        '<div class="score-card">'
        '<div class="score-label">REPOSITORY SCORE</div>'
        f'<div class="score-value">{score}<span>/100</span></div>'
        f'<div class="score-band">{escape(score_band(report.score))}</div>'
        '<div class="score-track">'
        f'<span style="width: {percentage}%"></span></div>'
        "</div>"
        '<div class="signal-card signal-pass"><span>PASS</span>'
        f"<strong>{counts[CheckStatus.PASS]}</strong><small>verified checks</small></div>"
        '<div class="signal-card signal-partial"><span>PARTIAL</span>'
        f"<strong>{counts[CheckStatus.PARTIAL]}</strong><small>some evidence</small></div>"
        '<div class="signal-card signal-fail"><span>MISSING</span>'
        f"<strong>{counts[CheckStatus.FAIL]}</strong><small>needs attention</small></div>"
        '<div class="signal-card signal-opportunity"><span>AVAILABLE</span>'
        f"<strong>+{available}</strong><small>recoverable points</small></div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_repository_facts(report: ReviewReport) -> None:
    repository = report.repository
    facts = (
        ("LANGUAGE", repository.language or "Unknown"),
        ("DEFAULT BRANCH", repository.default_branch),
        ("STARS", f"{repository.stars:,}"),
        ("FORKS", f"{repository.forks:,}"),
        ("OPEN ISSUES", f"{repository.open_issues:,}"),
        ("LAST PUSH", _format_date(repository.pushed_at)),
        ("REVIEW FOCUS", report.review_mode.value),
        ("RULESET", report.ruleset_version),
    )
    fact_markup = "".join(
        f'<div class="repo-fact"><dt>{escape(label)}</dt><dd>{escape(value)}</dd></div>'
        for label, value in facts
    )
    st.markdown(f'<dl class="repo-facts">{fact_markup}</dl>', unsafe_allow_html=True)


def _render_downloads(report: ReviewReport) -> None:
    """Render deterministic Markdown and JSON report downloads."""
    filename = report.repository.reference.full_name.replace("/", "-")
    label_column, markdown_column, json_column = st.columns(
        [4.2, 1.25, 1.25], vertical_alignment="center"
    )
    with label_column:
        st.caption(
            "Portable reports contain findings and evidence—not README or source content."
        )
    with markdown_column:
        st.download_button(
            "Download Markdown",
            render_markdown_report(report),
            file_name=f"{filename}-review.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with json_column:
        st.download_button(
            "Download JSON",
            render_json_report(report),
            file_name=f"{filename}-review.json",
            mime="application/json",
            use_container_width=True,
        )


def _render_top_actions(
    report: ReviewReport, suggestions: Sequence[Suggestion]
) -> None:
    top_suggestions = tuple(suggestions[:3])
    projected_score = _projected_score(report.score, top_suggestions)
    st.markdown(
        '<h2 class="section-heading">HIGHEST-IMPACT ACTIONS</h2>',
        unsafe_allow_html=True,
    )
    if not top_suggestions:
        st.markdown(
            '<div class="empty-state">No open recommendations in the current ruleset.</div>',
            unsafe_allow_html=True,
        )
        return
    st.markdown(
        '<div class="projection-line">Complete these actions for up to '
        f"<strong>{_format_points(projected_score)}/100</strong></div>",
        unsafe_allow_html=True,
    )
    for index, suggestion in enumerate(top_suggestions, start=1):
        _render_suggestion(index, suggestion, report, detailed=False)


def _render_category_scores(report: ReviewReport) -> None:
    st.markdown(
        '<h2 class="section-heading">CATEGORY BREAKDOWN</h2>',
        unsafe_allow_html=True,
    )
    rows: list[str] = []
    for category_score in report.category_scores:
        ratio = category_score.points / category_score.max_points
        percentage = round(ratio * 100)
        rows.append(
            '<div class="category-row">'
            f'<div class="category-name">{escape(category_score.category)}</div>'
            '<div class="category-track" role="progressbar" aria-label="'
            f'{escape(category_score.category)} score" aria-valuemin="0" '
            f'aria-valuemax="100" aria-valuenow="{percentage}">'
            f'<span style="width: {percentage}%"></span>'
            "</div>"
            '<div class="category-points">'
            f"{_format_points(category_score.points)} / {category_score.max_points}"
            "</div>"
            "</div>"
        )
    st.markdown(
        f'<div class="category-list">{"".join(rows)}</div>', unsafe_allow_html=True
    )
    st.markdown(
        '<div class="method-note"><strong>Scoring:</strong> pass = full points, '
        "partial = half, missing = zero. Popularity metrics are not scored. "
        f"Ruleset {escape(report.ruleset_version)}; review focus changes recommendation "
        "order only.</div>",
        unsafe_allow_html=True,
    )


def _render_checks(report: ReviewReport) -> None:
    st.markdown(
        '<h2 class="section-heading">CHECK EXPLORER</h2>',
        unsafe_allow_html=True,
    )
    status_column, category_column, search_column = st.columns([1.6, 1.15, 1.45])
    with status_column:
        status_filter = st.radio(
            "Status",
            ["All", "Needs attention", "Passed"],
            index=1,
            horizontal=True,
            key="check_status_filter",
        )
    with category_column:
        category_label = st.selectbox(
            "Category",
            ["All categories", *(category.value for category in Category)],
            key="check_category_filter",
        )
    with search_column:
        search_query = st.text_input(
            "Search checks",
            placeholder="Title or evidence",
            key="check_search_query",
        )

    category_filter = (
        None if category_label == "All categories" else Category(category_label)
    )
    checks = _filter_checks(
        report.checks,
        status_filter=status_filter,
        category=category_filter,
        search_query=search_query,
    )
    st.markdown(
        '<div class="filter-result">Showing '
        f"<strong>{len(checks)}</strong> of {len(report.checks)} checks</div>",
        unsafe_allow_html=True,
    )
    if not checks:
        st.markdown(
            '<div class="empty-state">No checks match the current filters.</div>',
            unsafe_allow_html=True,
        )
        return

    for category in Category:
        matching = [check for check in checks if check.category == category]
        if not matching:
            continue
        earned = sum(check.points for check in matching)
        available = sum(check.max_points for check in matching)
        st.markdown(
            '<div class="check-group-heading">'
            f"<span>{escape(category)}</span>"
            f"<small>{_format_points(earned)}/{available} shown</small>"
            "</div>"
            f'<div class="check-list">{_check_rows_markup(matching, report)}</div>',
            unsafe_allow_html=True,
        )


def _check_rows_markup(checks: Sequence[ScoredCheck], report: ReviewReport) -> str:
    rows: list[str] = []
    for check in checks:
        status = STATUS_LABELS[check.status]
        status_class = check.status.value
        source_links = " ".join(
            '<a href="'
            f'{escape(_source_url(report, source))}" target="_blank" '
            'rel="noopener noreferrer"><code>'
            f"{escape(source)}</code></a>"
            for source in check.sources
        )
        source_markup = (
            f'<div class="target-file"><span>EVIDENCE FILES</span>{source_links}</div>'
            if source_links
            else ""
        )
        recommendation_markup = ""
        if check.status != CheckStatus.PASS:
            recommendation_markup = (
                '<div class="recommendation-details">'
                "<div><span>TARGET</span>"
                f"<p><code>{escape(check.target)}</code></p></div>"
                "<div><span>NEXT STEP</span>"
                f"<p>{escape(check.recommendation)}</p></div>"
                "</div>"
            )
        rows.append(
            '<div class="check-row">'
            '<div class="check-header">'
            f'<span class="status status-{status_class}">{status}</span>'
            f'<span class="check-title">{escape(check.title)}</span>'
            '<span class="check-points">'
            f"{_format_points(check.points)}/{check.max_points}"
            "</span></div>"
            f'<div class="check-evidence">{escape(check.evidence)}</div>'
            f"{source_markup}{recommendation_markup}"
            "</div>"
        )
    return "".join(rows)


def _source_url(report: ReviewReport, path: str) -> str:
    """Return a GitHub blob URL for one evidence path."""
    branch = quote(report.repository.default_branch, safe="")
    encoded_path = quote(path, safe="/")
    return f"{report.repository.html_url}/blob/{branch}/{encoded_path}"


def _filter_checks(
    checks: Sequence[ScoredCheck],
    *,
    status_filter: str,
    category: Category | None,
    search_query: str,
) -> tuple[ScoredCheck, ...]:
    """Return checks matching the presentation filters."""
    query = search_query.strip().casefold()
    filtered: list[ScoredCheck] = []
    for check in checks:
        if status_filter == "Needs attention" and check.status == CheckStatus.PASS:
            continue
        if status_filter == "Passed" and check.status != CheckStatus.PASS:
            continue
        if category is not None and check.category != category:
            continue
        searchable = " ".join(
            (check.title, check.evidence, check.category, check.check_id)
        ).casefold()
        if query and query not in searchable:
            continue
        filtered.append(check)
    return tuple(filtered)


def _render_suggestions(
    report: ReviewReport, suggestions: Sequence[Suggestion]
) -> None:
    st.markdown(
        '<h2 class="section-heading">IMPROVEMENT ISSUES</h2>',
        unsafe_allow_html=True,
    )
    if not suggestions:
        st.markdown(
            '<div class="empty-state">No open recommendations in the current ruleset.</div>',
            unsafe_allow_html=True,
        )
        return

    for index, suggestion in enumerate(suggestions[:8], start=1):
        _render_suggestion(index, suggestion, report, detailed=True)
    if len(suggestions) > 8:
        with st.expander(f"{len(suggestions) - 8} additional recommendations"):
            for index, suggestion in enumerate(suggestions[8:], start=9):
                _render_suggestion(index, suggestion, report, detailed=True)


def _render_suggestion(
    index: int,
    suggestion: Suggestion,
    report: ReviewReport,
    *,
    detailed: bool,
) -> None:
    priority_class = suggestion.priority.casefold()
    source_check = _source_check(report, suggestion)
    details = ""
    if detailed:
        details = (
            '<div class="recommendation-details">'
            "<div><span>WHY IT MATTERS</span>"
            f"<p>{escape(CATEGORY_IMPACT[suggestion.category])}</p></div>"
            "<div><span>CURRENT SIGNAL</span>"
            f"<p>{escape(source_check.evidence)}</p></div>"
            "</div>"
        )
    st.markdown(
        '<article class="recommendation-row">'
        f'<span class="recommendation-index">#{index:02d}</span>'
        '<div class="recommendation-content">'
        '<div class="recommendation-header">'
        f'<span class="priority priority-{priority_class}">'
        f"{escape(suggestion.priority.upper())}</span>"
        f"<strong>{escape(suggestion.title)}</strong>"
        f'<span class="recommendation-category">{escape(suggestion.category)}</span>'
        "</div>"
        f'<p class="recommendation-action">{escape(suggestion.action)}</p>'
        '<div class="target-file"><span>TARGET</span>'
        f"<code>{escape(source_check.target)}</code></div>"
        f"{details}</div>"
        '<span class="potential-points">'
        f"+{_format_points(suggestion.potential_points)} pts"
        "</span></article>",
        unsafe_allow_html=True,
    )


def _source_check(report: ReviewReport, suggestion: Suggestion) -> ScoredCheck:
    """Find the scored check that produced a suggestion."""
    for check in report.checks:
        if suggestion.check_id is not None and check.check_id == suggestion.check_id:
            return check
        if (
            suggestion.check_id is None
            and check.title == suggestion.title
            and check.category == suggestion.category
        ):
            return check
    raise ValueError(f"Suggestion has no matching check: {suggestion.title}")


def _check_counts(checks: Sequence[ScoredCheck]) -> dict[CheckStatus, int]:
    """Count checks by status, including statuses with zero matches."""
    return {
        status: sum(check.status == status for check in checks)
        for status in CheckStatus
    }


def _projected_score(score: float, suggestions: Sequence[Suggestion]) -> float:
    """Return the capped score available from the displayed suggestions."""
    return min(100.0, score + sum(item.potential_points for item in suggestions))


def _recent_repositories() -> tuple[str, ...]:
    value = st.session_state.get("recent_repositories", ())
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _remember_repository(repository: str) -> None:
    st.session_state["recent_repositories"] = list(
        _updated_recent_repositories(_recent_repositories(), repository)
    )


def _updated_recent_repositories(
    current: Sequence[str],
    repository: str,
    *,
    limit: int = RECENT_REPOSITORY_LIMIT,
) -> tuple[str, ...]:
    """Return a deduplicated most-recent-first repository list."""
    remaining = [item for item in current if item.casefold() != repository.casefold()]
    return tuple([repository, *remaining][:limit])


def _format_date(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d") if value else "Unknown"


def _format_points(value: float) -> str:
    return f"{value:g}"


if __name__ == "__main__":
    main()
