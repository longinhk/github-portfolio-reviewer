"""Small GitHub REST API client used to collect repository evidence."""

import base64
import binascii
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

import requests

from github_portfolio_reviewer.models import RepositoryReference, RepositorySnapshot

GITHUB_API_URL = "https://api.github.com"
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


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
        candidate = parsed.path.strip("/")

    parts = candidate.strip("/").split("/")
    if len(parts) != 2:
        raise InvalidRepositoryError(
            "Use the repository root URL, such as https://github.com/owner/repository."
        )

    owner, name = parts
    name = name.removesuffix(".git")
    if not OWNER_PATTERN.fullmatch(owner) or not REPOSITORY_PATTERN.fullmatch(name):
        raise InvalidRepositoryError("The repository owner or name is not valid.")
    return RepositoryReference(owner=owner, name=name)


class GitHubClient:
    """Fetch the small set of public GitHub resources needed by the analyzer."""

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        """Initialize the client with an optional token and injectable HTTP session."""
        self._timeout = timeout
        self._session = session or requests.Session()
        self._headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-portfolio-reviewer",
            "X-GitHub-Api-Version": "2026-03-10",
        }
        if token and token.strip():
            self._headers["Authorization"] = f"Bearer {token.strip()}"

    def fetch_repository(self, reference: RepositoryReference) -> RepositorySnapshot:
        """Collect metadata, README text, and file paths for a public repository."""
        encoded_name = quote(reference.full_name, safe="/")
        metadata = self._get_json(f"/repos/{encoded_name}")
        if not isinstance(metadata, Mapping):
            raise GitHubAPIError("GitHub returned unexpected repository metadata.")

        canonical_reference = parse_repository_reference(
            _required_string(metadata, "full_name")
        )
        encoded_name = quote(canonical_reference.full_name, safe="/")
        default_branch = _required_string(metadata, "default_branch")
        readme = self._fetch_readme(encoded_name)
        repository_size = metadata.get("size")
        if (
            isinstance(repository_size, int)
            and not isinstance(repository_size, bool)
            and repository_size == 0
        ):
            files, truncated = (), False
        else:
            files, truncated = self._fetch_tree(encoded_name, default_branch)

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

        return RepositorySnapshot(
            reference=canonical_reference,
            html_url=_string_value(
                metadata,
                "html_url",
                default=f"https://github.com/{canonical_reference.full_name}",
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
            tree_truncated=truncated,
        )

    def _fetch_readme(self, encoded_name: str) -> str | None:
        payload = self._get_json(f"/repos/{encoded_name}/readme", allow_not_found=True)
        if payload is None:
            return None
        if not isinstance(payload, Mapping):
            raise GitHubAPIError("GitHub returned an unexpected README response.")

        content = payload.get("content")
        if not isinstance(content, str):
            return None
        try:
            compact_content = "".join(content.split())
            return base64.b64decode(compact_content, validate=True).decode(
                "utf-8", errors="replace"
            )
        except (binascii.Error, ValueError, TypeError) as error:
            raise GitHubAPIError("GitHub returned invalid README content.") from error

    def _fetch_tree(
        self, encoded_name: str, branch: str
    ) -> tuple[tuple[str, ...], bool]:
        encoded_branch = quote(branch, safe="")
        payload = self._get_json(
            f"/repos/{encoded_name}/git/trees/{encoded_branch}",
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
        files = tuple(
            str(item["path"])
            for item in tree
            if isinstance(item, Mapping)
            and item.get("type") == "blob"
            and isinstance(item.get("path"), str)
        )
        return files, bool(payload.get("truncated", False))

    def _get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        allow_not_found: bool = False,
        allow_conflict: bool = False,
    ) -> Any:
        url = f"{GITHUB_API_URL}{path}"
        try:
            response = self._session.get(
                url,
                headers=self._headers,
                params=params,
                timeout=self._timeout,
            )
        except requests.RequestException as error:
            raise GitHubAPIError(
                "Could not reach GitHub. Check your connection and try again."
            ) from error

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
                "GitHub rejected the token. Remove it or provide a valid token."
            )
        if response.status_code in {403, 429} and (
            response.status_code == 429
            or response.headers.get("Retry-After") is not None
            or response.headers.get("X-RateLimit-Remaining") == "0"
            or "rate limit" in _response_message(response).lower()
        ):
            reset = response.headers.get("X-RateLimit-Reset")
            reset_note = f" Reset time: {_format_reset_time(reset)}." if reset else ""
            raise RateLimitError(
                "GitHub API rate limit reached. Add a token or try again later."
                f"{reset_note}"
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


def _response_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except requests.JSONDecodeError:
        return ""
    if isinstance(payload, Mapping) and isinstance(payload.get("message"), str):
        return payload["message"]
    return ""


def _format_reset_time(timestamp: str) -> str:
    try:
        reset_time = datetime.fromtimestamp(int(timestamp)).astimezone()
    except (TypeError, ValueError, OSError):
        return "unknown"
    return reset_time.strftime("%Y-%m-%d %H:%M %Z")


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
