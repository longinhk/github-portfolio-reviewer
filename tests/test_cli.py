"""Tests for the portable command-line review interface."""

from collections.abc import Callable

from github_portfolio_reviewer import cli
from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import RepositorySnapshot, ReviewMode
from github_portfolio_reviewer.scoring import score_repository


def test_cli_emits_json_without_progress_when_quiet(
    make_snapshot: Callable[..., RepositorySnapshot],
    monkeypatch,
    capsys,
) -> None:
    snapshot = make_snapshot(files=("app.py",))
    report = score_repository(snapshot, analyze_repository(snapshot))
    received: dict[str, object] = {}

    def fake_review(repository: str, **kwargs):
        received.update(repository=repository, **kwargs)
        return report

    monkeypatch.setattr(cli, "review_repository", fake_review)

    result = cli.main(
        ["example/project", "--format", "json", "--focus", "backend", "--quiet"]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert '"schema_version"' in captured.out
    assert captured.err == ""
    assert received["repository"] == "example/project"
    assert received["review_mode"] == ReviewMode.BACKEND
    assert received["progress"] is None


def test_cli_reports_expected_review_errors(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "review_repository",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad input")),
    )

    assert cli.main(["bad", "--quiet"]) == 2
    assert "bad input" in capsys.readouterr().err
