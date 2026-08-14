"""Unit tests for repository input parsing and GitHub response handling."""

import base64
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
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
from github_portfolio_reviewer.models import RepositoryReference, RepositorySnapshot


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
        responses: list[FakeResponse | requests.RequestException] | None = None,
        *,
        error: requests.RequestException | None = None,
        auto_revision: bool = True,
    ) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.auto_revision = auto_revision
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        if self.auto_revision and "/git/ref/heads/" in url:
            return FakeResponse(200, {"object": {"sha": "a" * 40}})
        if not self.responses:
            raise AssertionError("No fake response remains for this request.")
        outcome = self.responses.pop(0)
        if isinstance(outcome, requests.RequestException):
            raise outcome
        return outcome


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


def tree_blob(path: str, sha: str | None, size: int | None) -> dict[str, object]:
    """Return one Git tree blob entry, including optional inspection metadata."""
    entry: dict[str, object] = {"path": path, "type": "blob"}
    if sha is not None:
        entry["sha"] = sha
    if size is not None:
        entry["size"] = size
    return entry


def encoded_blob(content: str | bytes) -> FakeResponse:
    """Return a valid base64 Git blob response for text or binary test content."""
    raw = content.encode() if isinstance(content, str) else content
    return FakeResponse(
        200,
        {
            "encoding": "base64",
            "content": base64.b64encode(raw).decode(),
        },
    )


def empty_snapshot(reference: RepositoryReference) -> RepositorySnapshot:
    """Return a compact snapshot for concurrency tests without HTTP."""
    return RepositorySnapshot(
        reference=reference,
        html_url=f"https://github.com/{reference.full_name}",
        description=None,
        default_branch="main",
        stars=0,
        forks=0,
        open_issues=0,
        language=None,
        topics=(),
        license_name=None,
        archived=False,
        fork=False,
        created_at=None,
        pushed_at=None,
        readme=None,
        files=(),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("example/project", "example/project"),
        (" https://github.com/example/project ", "example/project"),
        ("https://www.github.com/example/project.git", "example/project"),
        ("https://github.com/example/project/tree/main", "example/project"),
        (
            "https://github.com/example/project/tree/feature/docs",
            "example/project",
        ),
        (
            "https://github.com/example/project/blob/main/src/app.py",
            "example/project",
        ),
        ("git@github.com:example/project.git", "example/project"),
    ],
)
def test_parse_repository_reference_accepts_supported_inputs(
    value: str, expected: str
) -> None:
    assert parse_repository_reference(value).full_name == expected


def test_parse_tree_url_preserves_branch_and_subdirectory_segments() -> None:
    reference = parse_repository_reference(
        "https://github.com/example/project/tree/main/packages/api%20server"
    )

    assert reference == RepositoryReference(
        "example",
        "project",
        linked_tree_path=("main", "packages", "api server"),
    )


def test_parse_root_and_blob_urls_do_not_create_a_directory_scope() -> None:
    root = parse_repository_reference("https://github.com/example/project")
    blob = parse_repository_reference(
        "https://github.com/example/project/blob/main/packages/api/app.py"
    )

    assert root.linked_tree_path == ()
    assert blob.linked_tree_path == ()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example",
        "https://gitlab.com/example/project",
        "example/project/tree/main",
        "https://github.com/example/project/issues/1",
        "https://github.com/example/project/tree",
        "https://github.com/example/project/blob/main",
        "https://github.com:8443/example/project",
        "https://github.com/example/project?tab=readme",
        "https://github.com/example/project/tree/main/%2E%2E/secrets",
        "https://github.com/example/project/tree/main/%2Fetc",
        "https://github.com/example/project/tree/main/folder%5Cfile",
        "https://github.com/example/project/tree/main/%00folder",
        "https://github.com/example/project/tree/main/folder%ZZname",
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
    assert snapshot.commit_sha == "a" * 40
    assert snapshot.readme_path == "README.md"
    assert snapshot.files == ("README.md", "src/app.py")
    assert snapshot.tree_truncated is True
    assert session.calls[1]["url"].endswith(
        "/repos/renamed/project/git/ref/heads/feature%2Fdocs"
    )
    assert session.calls[2]["url"].endswith("/repos/renamed/project/readme")
    assert session.calls[2]["params"] == {"ref": "a" * 40}
    assert session.calls[3]["url"].endswith(
        f"/repos/renamed/project/git/trees/{'a' * 40}"
    )
    assert session.calls[3]["params"] == {"recursive": "1"}
    assert session.calls[0]["timeout"] == 4.0
    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"] == "2026-03-10"


def test_fetch_repository_scopes_evidence_to_linked_default_branch_folder() -> None:
    readme = "# API package\n\nInstall and usage instructions."
    scoped_contents = {
        "pyproject.toml": '[project]\nname = "api"\n',
        ".github/workflows/ci.yml": "permissions:\n  contents: read\n",
        "tests/test_api.py": "def test_api():\n    assert True\n",
    }
    tree = [
        tree_blob("pyproject.toml", "root-project", 20),
        tree_blob("packages/another/app.py", "another-app", 20),
        tree_blob("packages/api/README.md", "scoped-readme", len(readme)),
        *(
            tree_blob(
                f"packages/api/{path}",
                f"scoped-{index}",
                len(content.encode()),
            )
            for index, (path, content) in enumerate(scoped_contents.items())
        ),
        tree_blob("packages/apiary/app.py", "similarly-named", 20),
    ]
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(
                200,
                {"content": base64.b64encode(readme.encode()).decode()},
            ),
            FakeResponse(200, {"tree": tree, "truncated": False}),
            *(encoded_blob(content) for content in scoped_contents.values()),
        ]
    )
    reference = parse_repository_reference(
        "https://github.com/example/project/tree/main/packages/api"
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        reference,
        scope_to_linked_subdirectory=True,
    )

    assert snapshot.scope_path == "packages/api"
    assert snapshot.html_url == (
        "https://github.com/example/project/tree/main/packages/api"
    )
    assert snapshot.readme == readme
    assert snapshot.files == (
        "README.md",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "tests/test_api.py",
    )
    assert tuple(file.path for file in snapshot.inspected_files) == tuple(
        scoped_contents
    )
    assert tuple(file.content for file in snapshot.inspected_files) == tuple(
        scoped_contents.values()
    )
    assert session.calls[2]["url"].endswith(
        "/repos/example/project/readme/packages/api"
    )
    assert session.calls[2]["params"] == {"ref": "a" * 40}


def test_scoped_review_resolves_a_default_branch_containing_slashes() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                repository_metadata(default_branch="feature/docs"),
            ),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(
                200,
                {
                    "tree": [
                        tree_blob("packages/api/app.py", "app", 20),
                        tree_blob("packages/web/app.py", "web", 20),
                    ],
                    "truncated": False,
                },
            ),
        ]
    )
    reference = parse_repository_reference(
        "https://github.com/example/project/tree/feature/docs/packages/api"
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        reference,
        scope_to_linked_subdirectory=True,
    )

    assert snapshot.scope_path == "packages/api"
    assert snapshot.files == ("app.py",)
    assert session.calls[1]["url"].endswith("/git/ref/heads/feature%2Fdocs")
    assert session.calls[2]["params"] == {"ref": "a" * 40}


def test_scoped_review_rejects_a_non_default_branch_before_fetching_files() -> None:
    session = FakeSession(
        [FakeResponse(200, repository_metadata(default_branch="main"))]
    )
    reference = parse_repository_reference(
        "https://github.com/example/project/tree/feature/packages/api"
    )

    with pytest.raises(InvalidRepositoryError, match="default branch"):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            reference,
            scope_to_linked_subdirectory=True,
        )

    assert len(session.calls) == 1


def test_tree_url_keeps_whole_repository_behavior_without_scope_opt_in() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(
                200,
                {
                    "tree": [
                        tree_blob("root.py", "root", 20),
                        tree_blob("packages/api/app.py", "app", 20),
                    ],
                    "truncated": False,
                },
            ),
        ]
    )
    reference = parse_repository_reference(
        "https://github.com/example/project/tree/main/packages/api"
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        reference
    )

    assert snapshot.scope_path is None
    assert snapshot.html_url == "https://github.com/example/project"
    assert snapshot.files == ("root.py", "packages/api/app.py")
    assert session.calls[2]["url"].endswith("/repos/example/project/readme")
    assert session.calls[2]["params"] == {"ref": "a" * 40}


def test_scoped_review_rejects_a_missing_default_branch_folder() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(
                200,
                {
                    "tree": [tree_blob("packages/web/app.py", "web", 20)],
                    "truncated": False,
                },
            ),
        ]
    )
    reference = parse_repository_reference(
        "https://github.com/example/project/tree/main/packages/api"
    )

    with pytest.raises(InvalidRepositoryError, match="not found"):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            reference,
            scope_to_linked_subdirectory=True,
        )


def test_fetch_repository_collects_deterministic_bounded_text_evidence() -> None:
    contents = {
        "SECURITY.md": "# Security\n\nReport vulnerabilities privately.\n",
        ".github/dependabot.yml": "version: 2\nupdates: []\n",
        "pyproject.toml": '[project]\nname = "example"\n',
        ".github/workflows/ci.yml": "permissions:\n  contents: read\n",
        "tests/test_a.py": "def test_a():\n    assert True\n",
        "tests/test_b.py": "def test_b():\n    assert True\n",
        "tests/test_c.py": "def test_c():\n    assert True\n",
    }
    expected_paths = tuple(contents)
    tree = [
        tree_blob(path, f"sha-{index}", len(content.encode()))
        for index, (path, content) in enumerate(contents.items())
    ]
    tree.extend(
        [
            tree_blob("tests/test_d.py", "sha-extra-test", 20),
            tree_blob("tests/__init__.py", "sha-test-package", 0),
            tree_blob(".env", "sha-sensitive", 20),
            tree_blob("tests/fixture.png", "sha-binary", 20),
        ]
    )
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(200, {"tree": tree, "truncated": False}),
            *(encoded_blob(contents[path]) for path in expected_paths),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert tuple(file.path for file in snapshot.inspected_files) == expected_paths
    assert tuple(file.content for file in snapshot.inspected_files) == tuple(
        contents[path] for path in expected_paths
    )
    assert snapshot.inspection_truncated is True
    requested_urls = tuple(str(call["url"]) for call in session.calls)
    assert not any("sha-sensitive" in url for url in requested_urls)
    assert not any("sha-binary" in url for url in requested_urls)
    assert not any("sha-extra-test" in url for url in requested_urls)
    assert not any("sha-test-package" in url for url in requested_urls)


def test_inspection_reserves_slots_and_caps_blob_requests_at_ten_files() -> None:
    paths = (
        ".github/security.md",
        "SECURITY.md",
        ".github/dependabot.yml",
        "renovate.json",
        "pyproject.toml",
        "pytest.ini",
        "tox.ini",
        ".coveragerc",
        "codecov.yml",
        ".github/workflows/check-00.yml",
        ".github/workflows/check-01.yml",
        ".github/workflows/check-02.yml",
        "tests/test_00.py",
        "tests/test_01.py",
        "tests/test_02.py",
        "tests/test_03.py",
    )
    expected_paths = (
        ".github/security.md",
        ".github/dependabot.yml",
        "pyproject.toml",
        "pytest.ini",
        ".coveragerc",
        ".github/workflows/check-00.yml",
        ".github/workflows/check-01.yml",
        "tests/test_00.py",
        "tests/test_01.py",
        "tests/test_02.py",
    )
    tree = [tree_blob(path, f"blob-{index:02}", 20) for index, path in enumerate(paths)]
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(200, {"tree": tree, "truncated": False}),
            *(encoded_blob("name: CI\n") for _ in range(10)),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert tuple(file.path for file in snapshot.inspected_files) == expected_paths
    assert snapshot.inspection_truncated is True
    assert len(session.calls) == 14


def test_inspection_fetches_renovate_when_dependabot_is_absent() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(
                200,
                {
                    "tree": [tree_blob("renovate.json", "renovate", 20)],
                    "truncated": False,
                },
            ),
            encoded_blob('{"extends": ["config:recommended"]}'),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert tuple(file.path for file in snapshot.inspected_files) == ("renovate.json",)
    assert snapshot.inspection_truncated is False


@pytest.mark.parametrize(
    "path",
    [
        ".circleci/config.yml",
        ".gitlab-ci.yml",
        ".travis.yml",
        "azure-pipelines.yml",
        "Jenkinsfile",
    ],
)
def test_inspection_fetches_each_supported_ci_provider(path: str) -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(
                200,
                {
                    "tree": [tree_blob(path, "ci-config", 20)],
                    "truncated": False,
                },
            ),
            encoded_blob("provider configuration"),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert tuple(file.path for file in snapshot.inspected_files) == (path,)
    assert snapshot.inspection_truncated is False


def test_inspection_skips_oversized_missing_and_binary_evidence() -> None:
    tree = [
        tree_blob(".github/dependabot.yml", "dependabot", 20),
        tree_blob("SECURITY.md", None, 20),
        tree_blob("pyproject.toml", "pyproject", 100 * 1024 + 1),
        tree_blob(".github/workflows/ci.yml", "workflow", 20),
    ]
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(200, {"tree": tree, "truncated": False}),
            FakeResponse(404, {"message": "Not Found"}),
            encoded_blob(b"binary\x00content"),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert snapshot.inspected_files == ()
    assert snapshot.inspection_truncated is True
    blob_calls = [call for call in session.calls if "/git/blobs/" in str(call["url"])]
    assert len(blob_calls) == 2


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


def test_reused_client_returns_fresh_snapshot_from_instance_cache() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata(size=0)),
            FakeResponse(404, {"message": "Not Found"}),
        ]
    )
    client = GitHubClient(session=session)  # type: ignore[arg-type]
    reference = parse_repository_reference("example/project")

    first = client.fetch_repository(reference)
    second = client.fetch_repository(reference)

    assert second is first
    assert len(session.calls) == 2


def test_snapshot_cache_expires_after_default_five_minutes() -> None:
    current_time = [0.0]
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata(size=0)),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(200, repository_metadata(size=0)),
            FakeResponse(404, {"message": "Not Found"}),
        ]
    )
    client = GitHubClient(  # type: ignore[arg-type]
        session=session,
        clock=lambda: current_time[0],
    )
    reference = parse_repository_reference("example/project")

    first = client.fetch_repository(reference)
    current_time[0] = 299.0
    assert client.fetch_repository(reference) is first
    current_time[0] = 300.0
    refreshed = client.fetch_repository(reference)

    assert refreshed is not first
    assert len(session.calls) == 4


def test_snapshot_cache_is_bounded_to_thirty_two_repositories() -> None:
    responses: list[FakeResponse | requests.RequestException] = []
    for index in range(33):
        responses.extend(
            [
                FakeResponse(
                    200,
                    repository_metadata(full_name=f"example/project-{index}", size=0),
                ),
                FakeResponse(404, {"message": "Not Found"}),
            ]
        )
    session = FakeSession(responses)
    client = GitHubClient(session=session)  # type: ignore[arg-type]

    for index in range(33):
        client.fetch_repository(parse_repository_reference(f"example/project-{index}"))

    assert len(client._snapshot_cache) == 32
    assert "example/project-0" not in client._snapshot_cache
    assert "example/project-32" in client._snapshot_cache


def test_different_repository_fetches_are_not_globally_serialized() -> None:
    barrier = Barrier(2)

    class ConcurrentClient(GitHubClient):
        def _fetch_repository(
            self,
            reference: RepositoryReference,
            *,
            scope_to_linked_subdirectory: bool,
        ) -> RepositorySnapshot:
            barrier.wait(timeout=2)
            return empty_snapshot(reference)

    client = ConcurrentClient(cache_ttl=0)
    references = (
        RepositoryReference("example", "first"),
        RepositoryReference("example", "second"),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshots = tuple(executor.map(client.fetch_repository, references))

    assert tuple(snapshot.reference for snapshot in snapshots) == references


def test_same_repository_cold_fetches_are_coalesced() -> None:
    started = Event()
    release = Event()

    class CoalescingClient(GitHubClient):
        calls = 0

        def _fetch_repository(
            self,
            reference: RepositoryReference,
            *,
            scope_to_linked_subdirectory: bool,
        ) -> RepositorySnapshot:
            self.calls += 1
            started.set()
            assert release.wait(timeout=2)
            return empty_snapshot(reference)

    client = CoalescingClient()
    reference = RepositoryReference("example", "project")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.fetch_repository, reference)
        assert started.wait(timeout=2)
        second = executor.submit(client.fetch_repository, reference)
        release.set()
        first_snapshot = first.result(timeout=2)
        second_snapshot = second.result(timeout=2)

    assert client.calls == 1
    assert second_snapshot is first_snapshot
    assert client._fetch_locks == {}


def test_default_transport_uses_a_separate_session_per_worker_thread() -> None:
    barrier = Barrier(2)
    client = GitHubClient()

    def session_identity(_: int) -> int:
        barrier.wait(timeout=2)
        return id(client._session_for_current_thread())

    with ThreadPoolExecutor(max_workers=2) as executor:
        session_ids = tuple(executor.map(session_identity, range(2)))

    assert len(set(session_ids)) == 2


@pytest.mark.parametrize(
    "first_outcome",
    [
        requests.Timeout("temporary timeout"),
        FakeResponse(502, {"message": "Bad gateway"}),
        FakeResponse(503, {"message": "Unavailable"}),
        FakeResponse(504, {"message": "Gateway timeout"}),
    ],
)
def test_transient_failures_are_retried_once(
    first_outcome: FakeResponse | requests.RequestException,
) -> None:
    delays: list[float] = []
    session = FakeSession(
        [
            first_outcome,
            FakeResponse(200, repository_metadata(size=0)),
            FakeResponse(404, {"message": "Not Found"}),
        ]
    )

    snapshot = GitHubClient(  # type: ignore[arg-type]
        session=session,
        sleeper=delays.append,
    ).fetch_repository(parse_repository_reference("example/project"))

    assert snapshot.reference.full_name == "example/project"
    assert delays == [0.25]
    assert len(session.calls) == 3


def test_transient_response_is_attempted_at_most_twice() -> None:
    delays: list[float] = []
    session = FakeSession(
        [
            FakeResponse(503, {"message": "Unavailable"}),
            FakeResponse(503, {"message": "Still unavailable"}),
        ]
    )

    with pytest.raises(GitHubAPIError, match="status 503"):
        GitHubClient(  # type: ignore[arg-type]
            session=session,
            sleeper=delays.append,
        ).fetch_repository(parse_repository_reference("example/project"))

    assert delays == [0.25]
    assert len(session.calls) == 2


def test_failed_fetch_is_not_cached() -> None:
    session = FakeSession(
        [
            FakeResponse(500, {"message": "Server error"}),
            FakeResponse(500, {"message": "Server error"}),
            FakeResponse(200, repository_metadata(size=0)),
            FakeResponse(404, {"message": "Not Found"}),
        ]
    )
    client = GitHubClient(session=session)  # type: ignore[arg-type]
    reference = parse_repository_reference("example/project")

    with pytest.raises(GitHubAPIError, match="status 500"):
        client.fetch_repository(reference)
    snapshot = client.fetch_repository(reference)

    assert snapshot.reference.full_name == "example/project"
    assert len(session.calls) == 4


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
    retriable = response.status_code in {500, 502, 503, 504}
    responses = [response, response] if retriable else [response]
    session = FakeSession(responses)
    delays: list[float] = []
    with pytest.raises(exception_type):
        GitHubClient(  # type: ignore[arg-type]
            session=session,
            sleeper=delays.append,
        ).fetch_repository(parse_repository_reference("example/project"))
    assert len(session.calls) == (2 if retriable else 1)
    assert delays == ([0.25] if retriable else [])


def test_rate_limit_message_prefers_retry_after_for_public_requests() -> None:
    session = FakeSession(
        [
            FakeResponse(
                429,
                {"message": "Slow down"},
                headers={"Retry-After": "17"},
            )
        ]
    )

    with pytest.raises(RateLimitError) as captured:
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )

    assert "17 seconds" in str(captured.value)
    assert "optional GitHub token" in str(captured.value)
    assert len(session.calls) == 1


def test_authenticated_rate_limit_reports_utc_reset_without_token_advice() -> None:
    session = FakeSession(
        [
            FakeResponse(
                403,
                {"message": "API rate limit exceeded"},
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "0",
                },
            )
        ]
    )

    with pytest.raises(RateLimitError) as captured:
        GitHubClient(token="valid-token", session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )

    message = str(captured.value)
    assert "1970-01-01 00:00 UTC" in message
    assert "optional GitHub token" not in message
    assert len(session.calls) == 1


def test_network_failure_is_wrapped_without_leaking_token() -> None:
    session = FakeSession(error=requests.Timeout("request included secret-token"))
    with pytest.raises(GitHubAPIError) as captured:
        GitHubClient(  # type: ignore[arg-type]
            token="secret-token",
            session=session,
            sleeper=lambda _: None,
        ).fetch_repository(parse_repository_reference("example/project"))

    assert "secret-token" not in str(captured.value)
    assert len(session.calls) == 2


def test_malformed_json_is_rejected() -> None:
    session = FakeSession([FakeResponse(200, json_error=True)])
    with pytest.raises(GitHubAPIError, match="unreadable"):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )


def test_readme_path_and_revision_are_preserved() -> None:
    readme = "# Project"
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(
                200,
                {
                    "path": "ReadMe.rst",
                    "content": base64.b64encode(readme.encode()).decode(),
                },
            ),
            FakeResponse(200, {"tree": [], "truncated": False}),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    assert snapshot.commit_sha == "a" * 40
    assert snapshot.readme_path == "ReadMe.rst"
    assert session.calls[2]["params"] == {"ref": "a" * 40}
    assert f"/git/trees/{'a' * 40}" in str(session.calls[3]["url"])


def test_nonempty_repository_fails_safely_when_revision_cannot_be_resolved() -> None:
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
        ],
        auto_revision=False,
    )

    with pytest.raises(GitHubAPIError, match="stable revision"):
        GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
            parse_repository_reference("example/project")
        )

    assert len(session.calls) == 2


def test_optional_inspection_stops_after_repeated_transport_failure() -> None:
    tree = [
        tree_blob(".github/workflows/first.yml", "first", 20),
        tree_blob(".github/workflows/second.yml", "second", 20),
    ]
    session = FakeSession(
        [
            FakeResponse(200, repository_metadata()),
            FakeResponse(404, {"message": "Not Found"}),
            FakeResponse(200, {"tree": tree, "truncated": False}),
            requests.Timeout("first timeout"),
            requests.Timeout("second timeout"),
            encoded_blob("name: should-not-be-requested"),
        ]
    )

    snapshot = GitHubClient(session=session).fetch_repository(  # type: ignore[arg-type]
        parse_repository_reference("example/project")
    )

    blob_calls = [call for call in session.calls if "/git/blobs/" in str(call["url"])]
    assert len(blob_calls) == 2
    assert all(call["timeout"] == 4.0 for call in blob_calls)
    assert snapshot.inspected_files == ()
    assert snapshot.inspection_truncated is True


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
