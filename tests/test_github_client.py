"""Unit tests for repository input parsing and GitHub response handling."""

import base64
from collections.abc import Mapping
from typing import Any

import pytest
import requests

from github_portfolio_reviewer.github_client import (
    AuthenticationError,
    GitHubAPIError,
    GitHubClient,
    InvalidRepositoryError,
    RateLimitError,
    RepositoryNotFoundError,
    parse_repository_reference,
)


class FakeResponse:
    """Minimal requests.Response substitute for deterministic client tests."""

    def __init__(
        self,
        status_code: int,
        payload: object = None,
        *,
        headers: Mapping[str, str] | None = None,
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.headers = dict(headers or {})
        self.json_error = json_error

    def json(self) -> object:
        if self.json_error:
            raise requests.JSONDecodeError("invalid", "", 0)
        return self.payload


class FakeSession:
    """Queue responses and record every request made by GitHubClient."""

    def __init__(
        self,
        responses: list[FakeResponse] | None = None,
        *,
        error: requests.RequestException | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        if not self.responses:
            raise AssertionError("No fake response remains for this request.")
        return self.responses.pop(0)


def repository_metadata(**overrides: object) -> dict[str, object]:
    """Return a valid, compact repository metadata response."""
    metadata: dict[str, object] = {
        "full_name": "example/project",
        "html_url": "https://github.com/example/project",
        "description": "A sufficiently detailed repository description for testing.",
        "default_branch": "main",
        "size": 10,
        "stargazers_count": 7,
        "forks_count": 2,
        "open_issues_count": 1,
        "language": "Python",
        "topics": ["python", "portfolio", "testing"],
        "license": {"name": "MIT License", "spdx_id": "MIT"},
        "archived": False,
        "fork": False,
        "created_at": "2025-01-01T00:00:00Z",
        "pushed_at": "2026-01-01T00:00:00Z",
    }
    metadata.update(overrides)
    return metadata


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example/project", "example/project"),
        (" https://github.com/example/project ", "example/project"),
        ("https://www.github.com/example/project.git", "example/project"),
        ("git@github.com:example/project.git", "example/project"),
    ],
)
def test_parse_repository_reference_accepts_supported_inputs(
    value: str, expected: str
) -> None:
    assert parse_repository_reference(value).full_name == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example",
        "https://gitlab.com/example/project",
        "https://github.com/example/project/tree/main",
        "https://github.com:8443/example/project",
        "https://github.com/example/project?tab=readme",
        "-invalid/project",
    ],
)
def test_parse_repository_reference_rejects_unsafe_or_ambiguous_inputs(
    value: str,
) -> None:
    with pytest.raises(InvalidRepositoryError):
        parse_repository_reference(value)


def test_fetch_repository_builds_snapshot_and_expected_requests() -> None:
    readme = "# Project\n\nUseful documentation."
    session = FakeSession(
        [
            FakeResponse(
                200,
                repository_metadata(
                    full_name="renamed/project", default_branch="feature/docs"
                ),
            ),
            FakeResponse(
                200,
                {"content": base64.b64encode(readme.encode()).decode()},
            ),
            FakeResponse(
                200,
                {
                    "tree": [
                        {"path": "README.md", "type": "blob"},
                        {"path": "src", "type": "tree"},
                        {"path": "src/app.py", "type": "blob"},
                    ],
                    "truncated": True,
                },
            ),
        ]
    )
    client = GitHubClient(token=" test-token ", timeout=4.0, session=session)  # type: ignore[arg-type]

    snapshot = client.fetch_repository(parse_repository_reference("example/project"))

    assert snapshot.reference.full_name == "renamed/project"
    assert snapshot.readme == readme
    assert snapshot.files == ("README.md", "src/app.py")
    assert snapshot.tree_truncated is True
    assert session.calls[1]["url"].endswith("/repos/renamed/project/readme")
    assert session.calls[2]["url"].endswith(
        "/repos/renamed/project/git/trees/feature%2Fdocs"
    )
    assert session.calls[2]["params"] == {"recursive": "1"}
    assert session.calls[0]["timeout"] == 4.0
    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2026-03-10"


def test_missing_readme_is_valid_absence() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(200, {"tree": [], "truncated": False}),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert snapshot.readme is None


def test_empty_repository_skips_tree_request() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata(size=0)),
            FakeResponse(404, {"message": "Not Found"}),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert snapshot.files == ()
    assert len(session.calls) == 2


def test_tree_conflict_is_treated_as_empty_repository() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(409, {"message": "Git Repository is empty"}),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert snapshot.files == ()


@pytest.mark.parametrize(
    ("response", "exception_type"),
    [
        (FakeResponse(404, {"message": "Not Found"}), RepositoryNotFoundError),
        (FakeResponse(401, {"message": "Bad credentials"}), AuthenticationError),
        (
            FakeResponse(403, {"message": "API rate limit exceeded"}),
            RateLimitError,
        ),
        (FakeResponse(429, {"message": "Slow down"}), RateLimitError),
        (FakeResponse(500, {"message": "Server error"}), GitHubAPIError),
    ],
)
def test_http_errors_map_to_domain_exceptions(
    response: FakeResponse, exception_type: type[Exception]
) -> None:
    session = FakeSession([response])
    with pytest.raises(exception_type):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )


def test_network_failure_is_wrapped_without_leaking_token() -> None:
    session = FakeSession(error=requests.Timeout("request included secret-token"))
    with pytest.raises(GitHubAPIError) as captured:
        GitHubClient(token="secret-token", session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )

    assert "secret-token" not in str(captured.value)


def test_malformed_json_is_rejected() -> None:
    session = FakeSession([FakeResponse(200, json_error=True)])
    with pytest.raises(GitHubAPIError, match="unreadable"):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )


def test_malformed_readme_base64_is_rejected() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(200, {"content": "this is not base64!!!"}),
        ]
    )
    with pytest.raises(GitHubAPIError, match="invalid README"):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )
