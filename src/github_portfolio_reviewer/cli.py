"""Command-line interface for portable repository reviews."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from github_portfolio_reviewer.github_client import GitHubClientError
from github_portfolio_reviewer.models import ReviewMode
from github_portfolio_reviewer.reporting import (
    render_json_report,
    render_markdown_report,
)
from github_portfolio_reviewer.service import review_repository

FOCUS_MODES = {
    "general": ReviewMode.GENERAL,
    "python": ReviewMode.PYTHON,
    "ai-ml": ReviewMode.AI_ML,
    "data-science": ReviewMode.DATA_SCIENCE,
    "backend": ReviewMode.BACKEND,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser."""
    parser = argparse.ArgumentParser(
        prog="portfolio-review",
        description=(
            "Review one public GitHub repository with deterministic, read-only rules."
        ),
    )
    parser.add_argument("repository", help="owner/repository or a GitHub URL")
    parser.add_argument(
        "--focus",
        choices=tuple(FOCUS_MODES),
        default="general",
        help="recommendation focus; the comparable score does not change",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        dest="output_format",
    )
    parser.add_argument(
        "--linked-folder",
        action="store_true",
        help="review the folder in a default-branch /tree/ URL",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write the report to this path instead of standard output",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="hide progress messages written to standard error",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one review and return a process exit code."""
    args = build_parser().parse_args(argv)
    progress = None if args.quiet else lambda message: print(message, file=sys.stderr)
    try:
        report = review_repository(
            args.repository,
            token=os.getenv("GITHUB_TOKEN") or None,
            review_mode=FOCUS_MODES[args.focus],
            scope_to_linked_subdirectory=args.linked_folder,
            progress=progress,
        )
        rendered = (
            render_json_report(report)
            if args.output_format == "json"
            else render_markdown_report(report)
        )
        if args.output is None:
            print(rendered)
        else:
            args.output.write_text(f"{rendered}\n", encoding="utf-8")
    except (GitHubClientError, OSError, ValueError) as error:
        print(f"portfolio-review: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())
