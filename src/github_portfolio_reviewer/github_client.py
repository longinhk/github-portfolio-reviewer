"""Small GitHub REST API client used to collect repository evidence."""

import base64
import binascii
import re
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from threading import Lock, RLock, local
from time import monotonic, sleep
from typing import Any
from urllib.parse import quote, unquote, urlparse

import requests

from github_portfolio_reviewer.conventions import is_ci_file
from github_portfolio_reviewer.models import (
    RepositoryReference,
    RepositorySnapshot,
    RepositoryTextFile,
)

GITHUB_API_URL = "https://api.github.com"
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_INSPECTED_FILES = 10
MAX_INSPECTED_FILE_BYTES = 100 * 1024
SNAPSHOT_CACHE_SIZE = 32
DEFAULT_CACHE_TTL_SECONDS = 5 * 60
RETRY_DELAY_SECONDS = 0.25
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}

TEST_CONFIG_NAMES = {
    "conftest.py",
    "noxfile.py",
    "pytest.ini",
    "setup.cfg",
    "tox.ini",
}
COVERAGE_CONFIG_NAMES = {
    ".coveragerc",
    "codecov.yaml",
    "codecov.yml",
    "coverage.toml",
}
TEST_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
SENSITIVE_FILE_NAMES = {
    "credentials.json",
    "id_dsa",
    "id_rsa",
}
SENSITIVE_FILE_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}

INSPECTION_BUCKET_LIMITS = (
    ("security_policy", 1),
    ("dependency_updater", 1),
    ("project_config", 1),
    ("test_config", 1),
    ("coverage_config", 1),
    ("workflow", 2),
    ("test_source", 3),
)


@dataclass(frozen=True, slots=True)
class _TreeBlob:
    """Git tree evidence retained privately for bounded content requests."""

    path: str
    sha: str | None
    size: int | None


class _FetchLock:
    """Track one repository-key lock and the callers currently using it."""

    __slots__ = ("lock", "users")

    def __init__(self) -> None:
        self.lock = Lock()
        self.users = 0


class GitHubClientError(Exception):
    """Base exception for expected GitHub client failures."""


class InvalidRepositoryError(GitHubClientError):
    """Raised when repository input cannot be parsed safely."""


class RepositoryNotFoundError(GitHubClientError):
    """Raised when GitHub cannot find or expose the requested repository."""


class AuthenticationError(GitHubClientError):
    """Raised when a supplied GitHub token is rejected."""


class RateLimitError(GitHubClientError):
    """Raised when the GitHub API request allowance has been exhausted."""


class GitHubAPIError(GitHubClientError):
    """Raised for an unexpected response or network failure."""


def parse_repository_reference(value: str) -> RepositoryReference:
    """Parse ``owner/repository`` or a standard GitHub URL.

    Args:
        value: User-entered repository identifier or URL.

    Raises:
        InvalidRepositoryError: If the value is empty, malformed, or not a GitHub URL.
    """
    candidate = value.strip()
    if not candidate:
        raise InvalidRepositoryError("Enter a GitHub repository URL or owner/name.")

    linked_tree_path: tuple[str, ...] = ()
    if candidate.startswith("git@github.com:"):
        candidate = candidate.removeprefix("git@github.com:")
    elif "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "github.com",
            "www.github.com",
        }:
            raise InvalidRepositoryError(
                "Only github.com repository URLs are supported."
            )
        if (
            parsed.netloc.casefold() not in {"github.com", "www.github.com"}
            or parsed.query
            or parsed.fragment
        ):
            raise InvalidRepositoryError(
                "Use a plain GitHub repository URL without credentials, ports, or query text."
            )
        parts = _safe_github_url_parts(parsed.path)
        if _is_supported_repository_subpath(parts):
            if parts[2] == "tree":
                linked_tree_path = tuple(parts[3:])
            parts = parts[:2]
        candidate = "/".join(parts)

    parts = candidate.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise InvalidRepositoryError(
            "Use the repository root URL, such as https://github.com/owner/repository."
        )

    owner, name = parts
    name = name.removesuffix(".git")
    if not OWNER_PATTERN.fullmatch(owner) or not REPOSITORY_PATTERN.fullmatch(name):
        raise InvalidRepositoryError("The repository owner or name is not valid.")
    return RepositoryReference(
        owner=owner,
        name=name,
        linked_tree_path=linked_tree_path,
    )


def _safe_github_url_parts(path: str) -> list[str]:
    """Decode URL path segments while rejecting ambiguous traversal-like input."""
    raw_parts = path.strip("/").split("/")
    parts: list[str] = []
    for raw_part in raw_parts:
        if re.search(r"%(?![0-9A-Fa-f]{2})", raw_part):
            raise InvalidRepositoryError("The repository URL contains an unsafe path.")
        part = unquote(raw_part)
        if (
            not part
            or part in {".", ".."}
            or "/" in part
            or "\\" in part
            or any(ord(character) < 32 for character in part)
        ):
            raise InvalidRepositoryError("The repository URL contains an unsafe path.")
        parts.append(part)
    return parts


def _is_supported_repository_subpath(parts: list[str]) -> bool:
    """Return whether a GitHub URL safely identifies a tree or blob below a repo."""
    if len(parts) >= 4 and parts[2] == "tree":
        return bool(parts[3])
    if len(parts) >= 5 and parts[2] == "blob":
        return bool(parts[3] and parts[4])
    return False


class GitHubClient:
    """Fetch the small set of public GitHub resources needed by the analyzer."""

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: float = 10.0,
        optional_timeout: float = 4.0,
        session: requests.Session | None = None,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        """Initialize the client with optional auth and injectable test boundaries."""
        self._timeout = timeout
        self._optional_timeout = min(timeout, optional_timeout)
        self._provided_session = session
        self._thread_state = local()
        self._cache_ttl = cache_ttl
        self._clock = clock
        self._sleeper = sleeper
        self._snapshot_cache: OrderedDict[str, tuple[float, RepositorySnapshot]] = (
            OrderedDict()
        )
        self._cache_lock = RLock()
        self._fetch_locks: dict[str, _FetchLock] = {}
        self._headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-portfolio-reviewer",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if token and token.strip():
            self._headers["Authorization"] = f"Bearer {token.strip()}"

    def fetch_repository(
        self,
        reference: RepositoryReference,
        *,
        scope_to_linked_subdirectory: bool = False,
    ) -> RepositorySnapshot:
        """Collect evidence for a repository or its linked default-branch folder."""
        linked_tree_path = (
            reference.linked_tree_path if scope_to_linked_subdirectory else ()
        )
        cache_key = _snapshot_cache_key(reference, linked_tree_path)
        cached = self._cached_snapshot(cache_key)
        if cached is not None:
            return cached

        fetch_lock = self._acquire_fetch_lock(cache_key)
        try:
            cached = self._cached_snapshot(cache_key)
            if cached is not None:
                return cached
            snapshot = self._fetch_repository(
                reference,
                scope_to_linked_subdirectory=scope_to_linked_subdirectory,
            )
            self._store_snapshot(cache_key, snapshot)
            return snapshot
        finally:
            self._release_fetch_lock(cache_key, fetch_lock)

    def _fetch_repository(
        self,
        reference: RepositoryReference,
        *,
        scope_to_linked_subdirectory: bool,
    ) -> RepositorySnapshot:
        """Collect one uncached immutable snapshot without serializing other reviews."""
        linked_tree_path = (
            reference.linked_tree_path if scope_to_linked_subdirectory else ()
        )

        encoded_name = quote(reference.full_name, safe="/")
        metadata = self._get_json(f"/repos/{encoded_name}")
        if not isinstance(metadata, Mapping):
            raise GitHubAPIError("GitHub returned unexpected repository metadata.")

        canonical_reference = parse_repository_reference(
            _required_string(metadata, "full_name")
        )
        encoded_name = quote(canonical_reference.full_name, safe="/")
        default_branch = _required_string(metadata, "default_branch")
        scope_path = _resolve_linked_subdirectory(linked_tree_path, default_branch)
        repository_size = metadata.get("size")
        repository_is_empty = (
            isinstance(repository_size, int)
            and not isinstance(repository_size, bool)
            and repository_size == 0
        )
        commit_sha = None
        if not repository_is_empty:
            commit_sha = self._fetch_revision_sha(encoded_name, default_branch)
        readme, readme_path = self._fetch_readme(
            encoded_name,
            revision=commit_sha or default_branch,
            scope_path=scope_path,
        )
        if repository_is_empty:
            blobs, tree_truncated = (), False
        else:
            blobs, tree_truncated = self._fetch_tree(
                encoded_name, commit_sha or default_branch
            )
        if scope_path is not None:
            blobs = _scope_tree_blobs(blobs, scope_path)
            if not blobs and not tree_truncated:
                raise InvalidRepositoryError(
                    "The linked subdirectory was not found on the default branch."
                )
        files = tuple(blob.path for blob in blobs)
        inspected_files, inspection_truncated = self._fetch_inspected_files(
            encoded_name, blobs
        )
        inspection_truncated = inspection_truncated or tree_truncated

        license_data = metadata.get("license")
        license_name = None
        if isinstance(license_data, Mapping):
            spdx_id = _optional_string(license_data.get("spdx_id"))
            if spdx_id and spdx_id != "NOASSERTION":
                license_name = _optional_string(license_data.get("name")) or spdx_id
        topics_data = metadata.get("topics")
        topics = (
            tuple(str(topic) for topic in topics_data if isinstance(topic, str))
            if isinstance(topics_data, list)
            else ()
        )

        snapshot = RepositorySnapshot(
            reference=canonical_reference,
            html_url=_scoped_html_url(
                _string_value(
                    metadata,
                    "html_url",
                    default=f"https://github.com/{canonical_reference.full_name}",
                ),
                default_branch=default_branch,
                scope_path=scope_path,
            ),
            description=_optional_string(metadata.get("description")),
            default_branch=default_branch,
            stars=_integer_value(metadata, "stargazers_count"),
            forks=_integer_value(metadata, "forks_count"),
            open_issues=_integer_value(metadata, "open_issues_count"),
            language=_optional_string(metadata.get("language")),
            topics=topics,
            license_name=license_name,
            archived=bool(metadata.get("archived", False)),
            fork=bool(metadata.get("fork", False)),
            created_at=_parse_datetime(metadata.get("created_at")),
            pushed_at=_parse_datetime(metadata.get("pushed_at")),
            readme=readme,
            files=files,
            tree_truncated=tree_truncated,
            inspected_files=inspected_files,
            inspection_truncated=inspection_truncated,
            scope_path=scope_path,
            commit_sha=commit_sha,
            readme_path=readme_path,
        )
        return snapshot

    def _cached_snapshot(self, key: str) -> RepositorySnapshot | None:
        """Return a fresh cached snapshot and discard expired entries on access."""
        with self._cache_lock:
            if self._cache_ttl <= 0:
                return None
            cached = self._snapshot_cache.get(key)
            if cached is None:
                return None
            stored_at, snapshot = cached
            if self._clock() - stored_at >= self._cache_ttl:
                del self._snapshot_cache[key]
                return None
            self._snapshot_cache.move_to_end(key)
            return snapshot

    def _store_snapshot(self, key: str, snapshot: RepositorySnapshot) -> None:
        """Store one immutable snapshot in the bounded thread-safe cache."""
        with self._cache_lock:
            if self._cache_ttl <= 0:
                return
            self._snapshot_cache[key] = (self._clock(), snapshot)
            self._snapshot_cache.move_to_end(key)
            while len(self._snapshot_cache) > SNAPSHOT_CACHE_SIZE:
                self._snapshot_cache.popitem(last=False)

    def _acquire_fetch_lock(self, key: str) -> _FetchLock:
        """Serialize only cold fetches for the same repository cache key."""
        with self._cache_lock:
            fetch_lock = self._fetch_locks.get(key)
            if fetch_lock is None:
                fetch_lock = _FetchLock()
                self._fetch_locks[key] = fetch_lock
            fetch_lock.users += 1
        fetch_lock.lock.acquire()
        return fetch_lock

    def _release_fetch_lock(self, key: str, fetch_lock: _FetchLock) -> None:
        """Release and discard a per-key lock after its final caller exits."""
        fetch_lock.lock.release()
        with self._cache_lock:
            fetch_lock.users -= 1
            if fetch_lock.users == 0 and self._fetch_locks.get(key) is fetch_lock:
                del self._fetch_locks[key]

    def _fetch_readme(
        self,
        encoded_name: str,
        *,
        revision: str,
        scope_path: str | None,
    ) -> tuple[str | None, str | None]:
        endpoint = f"/repos/{encoded_name}/readme"
        params = {"ref": revision}
        if scope_path is not None:
            endpoint = f"{endpoint}/{quote(scope_path, safe='/')}"
        payload = self._get_json(
            endpoint,
            params=params,
            allow_not_found=True,
        )
        if payload is None:
            return None, None
        if not isinstance(payload, Mapping):
            raise GitHubAPIError("GitHub returned an unexpected README response.")

        content = payload.get("content")
        if not isinstance(content, str):
            return None, None
        try:
            compact_content = "".join(content.split())
            readme = base64.b64decode(compact_content, validate=True).decode(
                "utf-8", errors="replace"
            )
        except (binascii.Error, ValueError, TypeError) as error:
            raise GitHubAPIError("GitHub returned invalid README content.") from error
        path = _optional_string(payload.get("path"))
        if path is not None and scope_path is not None:
            path = path.removeprefix(f"{scope_path}/")
        return readme, path or "README.md"

    def _fetch_revision_sha(self, encoded_name: str, branch: str) -> str:
        """Resolve the moving default branch to one immutable commit SHA."""
        encoded_branch = quote(branch, safe="")
        payload = self._get_json(
            f"/repos/{encoded_name}/git/ref/heads/{encoded_branch}",
            allow_not_found=True,
            allow_conflict=True,
        )
        if payload is None:
            raise GitHubAPIError(
                "GitHub could not resolve the default branch to a stable revision."
            )
        if not isinstance(payload, Mapping):
            raise GitHubAPIError("GitHub returned an unexpected branch response.")
        target = payload.get("object")
        if not isinstance(target, Mapping):
            raise GitHubAPIError("GitHub branch data did not identify a revision.")
        return _required_string(target, "sha")

    def _fetch_tree(
        self, encoded_name: str, revision: str
    ) -> tuple[tuple[_TreeBlob, ...], bool]:
        encoded_revision = quote(revision, safe="")
        payload = self._get_json(
            f"/repos/{encoded_name}/git/trees/{encoded_revision}",
            params={"recursive": "1"},
            allow_conflict=True,
        )
        if payload is None:
            return (), False
        if not isinstance(payload, Mapping):
            raise GitHubAPIError("GitHub returned an unexpected file-tree response.")

        tree = payload.get("tree")
        if not isinstance(tree, list):
            raise GitHubAPIError("The GitHub response did not contain a file tree.")
        blobs = tuple(
            _tree_blob(item)
            for item in tree
            if isinstance(item, Mapping)
            and item.get("type") == "blob"
            and isinstance(item.get("path"), str)
        )
        return blobs, bool(payload.get("truncated", False))

    def _fetch_inspected_files(
        self, encoded_name: str, blobs: tuple[_TreeBlob, ...]
    ) -> tuple[tuple[RepositoryTextFile, ...], bool]:
        """Fetch a small deterministic set of text files needed by deeper checks."""
        candidates, truncated = _inspection_candidates(blobs)
        fetchable: list[_TreeBlob] = []
        for blob in candidates:
            if blob.sha is None:
                truncated = True
                continue
            if blob.size is not None and blob.size > MAX_INSPECTED_FILE_BYTES:
                truncated = True
                continue
            fetchable.append(blob)

        if len(fetchable) > MAX_INSPECTED_FILES:
            truncated = True
            fetchable = fetchable[:MAX_INSPECTED_FILES]

        inspected: list[RepositoryTextFile] = []
        for blob in fetchable:
            try:
                content = self._fetch_blob_text(encoded_name, blob.sha)
            except (GitHubAPIError, RateLimitError):
                truncated = True
                break
            if content is None:
                truncated = True
                continue
            inspected.append(RepositoryTextFile(path=blob.path, content=content))
        return tuple(inspected), truncated

    def _fetch_blob_text(self, encoded_name: str, sha: str) -> str | None:
        """Return one UTF-8 Git blob, or ``None`` when optional evidence is unusable."""
        encoded_sha = quote(sha, safe="")
        payload = self._get_json(
            f"/repos/{encoded_name}/git/blobs/{encoded_sha}",
            allow_not_found=True,
            timeout=self._optional_timeout,
        )
        if not isinstance(payload, Mapping) or payload.get("encoding") != "base64":
            return None
        content = payload.get("content")
        if not isinstance(content, str):
            return None
        try:
            raw = base64.b64decode("".join(content.split()), validate=True)
        except (binascii.Error, ValueError, TypeError):
            return None
        if len(raw) > MAX_INSPECTED_FILE_BYTES or b"\x00" in raw:
            return None
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        allow_not_found: bool = False,
        allow_conflict: bool = False,
        timeout: float | None = None,
    ) -> Any:
        url = f"{GITHUB_API_URL}{path}"
        response = self._request_with_retry(url, params=params, timeout=timeout)

        if response.status_code == 404:
            if allow_not_found:
                return None
            raise RepositoryNotFoundError(
                "Repository not found. Confirm that it is public and the URL is correct."
            )
        if response.status_code == 409 and allow_conflict:
            return None
        if response.status_code == 401:
            raise AuthenticationError(
                "GitHub rejected the configured token. Replace it or use public access."
            )
        if response.status_code in {403, 429} and (
            response.status_code == 429
            or response.headers.get("Retry-After") is not None
            or response.headers.get("X-RateLimit-Remaining") == "0"
            or "rate limit" in _response_message(response).lower()
        ):
            raise RateLimitError(
                _rate_limit_message(
                    response,
                    authenticated="Authorization" in self._headers,
                )
            )
        if not 200 <= response.status_code < 300:
            message = _response_message(response)
            detail = f": {message}" if message else ""
            raise GitHubAPIError(
                f"GitHub API request failed with status {response.status_code}{detail}"
            )

        try:
            return response.json()
        except requests.JSONDecodeError as error:
            raise GitHubAPIError("GitHub returned an unreadable response.") from error

    def _request_with_retry(
        self,
        url: str,
        *,
        params: Mapping[str, str] | None,
        timeout: float | None,
    ) -> requests.Response:
        """Make one GET and retry once only for transient transport/server failures."""
        last_error: requests.RequestException | None = None
        session = self._session_for_current_thread()
        for attempt in range(2):
            try:
                response = session.get(
                    url,
                    headers=self._headers,
                    params=params,
                    timeout=self._timeout if timeout is None else timeout,
                )
            except requests.RequestException as error:
                last_error = error
                if attempt == 0:
                    self._sleeper(RETRY_DELAY_SECONDS)
                    continue
                break

            if response.status_code in RETRIABLE_STATUS_CODES and attempt == 0:
                self._sleeper(RETRY_DELAY_SECONDS)
                continue
            return response

        raise GitHubAPIError(
            "Could not reach GitHub. Check your connection and try again."
        ) from last_error

    def _session_for_current_thread(self) -> requests.Session:
        """Return the injected transport or one reusable Session per worker thread."""
        if self._provided_session is not None:
            return self._provided_session
        session = getattr(self._thread_state, "session", None)
        if session is None:
            session = requests.Session()
            self._thread_state.session = session
        return session


def _tree_blob(item: Mapping[str, object]) -> _TreeBlob:
    """Convert one validated Git tree item without exposing its raw mapping."""
    sha_value = item.get("sha")
    sha = sha_value if isinstance(sha_value, str) and sha_value else None
    size_value = item.get("size")
    size = (
        size_value
        if isinstance(size_value, int)
        and not isinstance(size_value, bool)
        and size_value >= 0
        else None
    )
    return _TreeBlob(path=str(item["path"]), sha=sha, size=size)


def _snapshot_cache_key(
    reference: RepositoryReference, linked_tree_path: tuple[str, ...]
) -> str:
    """Return a cache key that keeps whole-repository and scoped evidence separate."""
    key = reference.full_name.casefold()
    if linked_tree_path:
        return f"{key}::tree/{'/'.join(linked_tree_path)}"
    return key


def _resolve_linked_subdirectory(
    linked_tree_path: tuple[str, ...], default_branch: str
) -> str | None:
    """Resolve tree-link segments only when they target the default branch."""
    if not linked_tree_path:
        return None
    branch_parts = tuple(default_branch.split("/"))
    if linked_tree_path[: len(branch_parts)] != branch_parts:
        raise InvalidRepositoryError(
            "Subdirectory review only supports links on the default branch."
        )
    relative_parts = linked_tree_path[len(branch_parts) :]
    return "/".join(relative_parts) or None


def _scope_tree_blobs(
    blobs: tuple[_TreeBlob, ...], scope_path: str
) -> tuple[_TreeBlob, ...]:
    """Keep blobs below one directory and make their paths scope-relative."""
    prefix = f"{scope_path}/"
    return tuple(
        _TreeBlob(
            path=blob.path.removeprefix(prefix),
            sha=blob.sha,
            size=blob.size,
        )
        for blob in blobs
        if blob.path.startswith(prefix) and blob.path != prefix
    )


def _scoped_html_url(
    repository_url: str,
    *,
    default_branch: str,
    scope_path: str | None,
) -> str:
    """Return the canonical repository or default-branch subdirectory URL."""
    if scope_path is None:
        return repository_url
    encoded_branch = quote(default_branch, safe="/")
    encoded_scope = quote(scope_path, safe="/")
    return f"{repository_url.rstrip('/')}/tree/{encoded_branch}/{encoded_scope}"


def _inspection_candidates(
    blobs: tuple[_TreeBlob, ...],
) -> tuple[tuple[_TreeBlob, ...], bool]:
    """Select evidence with reserved slots so one category cannot starve another."""
    buckets: dict[str, list[tuple[str, _TreeBlob]]] = {
        name: [] for name, _ in INSPECTION_BUCKET_LIMITS
    }
    for blob in blobs:
        bucket = _inspection_bucket(blob.path)
        if bucket is None:
            continue
        buckets[bucket].append((_normalize_path(blob.path), blob))

    selected: list[_TreeBlob] = []
    truncated = False
    for bucket, limit in INSPECTION_BUCKET_LIMITS:
        candidates = sorted(buckets[bucket], key=lambda candidate: candidate[0])
        if len(candidates) > limit:
            truncated = True
        selected.extend(blob for _, blob in candidates[:limit])

    if len(selected) > MAX_INSPECTED_FILES:
        raise RuntimeError("Inspection bucket limits exceed the global file limit.")
    return tuple(selected), truncated


def _inspection_bucket(path: str) -> str | None:
    """Return the reserved bounded-inspection bucket for one safe text path."""
    normalized = _normalize_path(path)
    pure_path = PurePosixPath(normalized)
    name = pure_path.name
    if _is_sensitive_filename(name):
        return None
    if normalized in {
        ".github/security.md",
        "docs/security.md",
        "security.md",
    }:
        return "security_policy"
    if normalized in {
        ".github/dependabot.yaml",
        ".github/dependabot.yml",
        "renovate.json",
        "renovate.json5",
    }:
        return "dependency_updater"
    if normalized == "pyproject.toml":
        return "project_config"
    if name in TEST_CONFIG_NAMES and (
        len(pure_path.parts) == 1 or pure_path.parts[0] in {"test", "tests"}
    ):
        return "test_config"
    if name in COVERAGE_CONFIG_NAMES and len(pure_path.parts) == 1:
        return "coverage_config"
    if is_ci_file(normalized):
        return "workflow"
    if _is_test_source(pure_path):
        return "test_source"
    return None


def _is_sensitive_filename(name: str) -> bool:
    """Return whether a filename should never be fetched for optional inspection."""
    return bool(
        name == ".env"
        or name.startswith(".env.")
        or name in SENSITIVE_FILE_NAMES
        or PurePosixPath(name).suffix in SENSITIVE_FILE_SUFFIXES
    )


def _is_test_source(path: PurePosixPath) -> bool:
    """Return whether a path is a conventionally named text-based test source."""
    if path.suffix not in TEST_SOURCE_SUFFIXES:
        return False
    if path.name in {"__init__.py", "conftest.py", "factories.py", "fixtures.py"}:
        return False
    directories = set(path.parts[:-1])
    if directories & {"__tests__", "spec", "specs", "test", "tests"}:
        return True
    return bool(
        re.fullmatch(r"test_.+\.py", path.name)
        or re.fullmatch(r".+_test\.py", path.name)
        or re.fullmatch(r".+\.(?:spec|test)\.[jt]sx?", path.name)
    )


def _normalize_path(path: str) -> str:
    """Normalize a Git tree path for deterministic matching and sorting."""
    return path.replace("\\", "/").strip("/").casefold()


def _response_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except requests.JSONDecodeError:
        return ""
    if isinstance(payload, Mapping) and isinstance(payload.get("message"), str):
        return payload["message"]
    return ""


def _rate_limit_message(response: requests.Response, *, authenticated: bool) -> str:
    """Build actionable rate-limit guidance without exposing request credentials."""
    retry_after = response.headers.get("Retry-After")
    reset = response.headers.get("X-RateLimit-Reset")
    if retry_after and retry_after.isdecimal():
        timing = f"Try again in {retry_after} seconds."
    elif reset:
        timing = f"Try again after {_format_reset_time(reset)}."
    else:
        timing = "Wait at least one minute before trying again."
    token_note = (
        ""
        if authenticated
        else " An optional GitHub token provides a higher request limit."
    )
    return f"GitHub API rate limit reached. {timing}{token_note}"


def _format_reset_time(timestamp: str) -> str:
    try:
        reset_time = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (TypeError, ValueError, OSError):
        return "unknown"
    return reset_time.strftime("%Y-%m-%d %H:%M UTC")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _string_value(mapping: Mapping[str, object], key: str, *, default: str) -> str:
    value = mapping.get(key)
    return value if isinstance(value, str) and value else default


def _required_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise GitHubAPIError(f"GitHub metadata is missing the required '{key}' field.")
    return value


def _integer_value(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
