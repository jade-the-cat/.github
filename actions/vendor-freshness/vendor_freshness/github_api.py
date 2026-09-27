"""The four GitHub REST reads the freshness check needs, over the standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Protocol

API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT_SECONDS = 30


class ApiError(Exception):
    """A GitHub API answer the check cannot use. Never carries the token."""


class SourceApi(Protocol):
    """What the checks read from the owner repository (a fake stands in for tests)."""

    def file_bytes(self, repository: str, path: str, ref: str) -> bytes | None: ...

    def latest_release(self, repository: str) -> str | None: ...

    def tag_commit(self, repository: str, tag: str) -> str | None: ...

    def compare(self, repository: str, base: str, head: str) -> str: ...


Opener = Callable[[urllib.request.Request, float], object]


class GitHubApi:
    """Reads files, releases, tags and comparisons with an installation or user token."""

    def __init__(self, token: str, base_url: str = API_URL, opener: Opener | None = None) -> None:
        self._token = token
        self._base = base_url.rstrip("/")
        self._open = opener or (lambda request, timeout: urllib.request.urlopen(request, timeout=timeout))

    def file_bytes(self, repository: str, path: str, ref: str) -> bytes | None:
        """The file's bytes at `ref`, or None when the file does not exist there."""
        quoted = urllib.parse.quote(path)
        query = urllib.parse.urlencode({"ref": ref})
        return self._get(f"/repos/{repository}/contents/{quoted}?{query}", "application/vnd.github.raw+json")

    def latest_release(self, repository: str) -> str | None:
        """The tag of the newest published, non-prerelease release, or None if there is none."""
        body = self._get(f"/repos/{repository}/releases/latest")
        return None if body is None else str(json.loads(body)["tag_name"])

    def tag_commit(self, repository: str, tag: str) -> str | None:
        """The commit a tag names (annotated tags are followed), or None if the tag is missing."""
        body = self._get(f"/repos/{repository}/git/ref/tags/{urllib.parse.quote(tag)}")
        if body is None:
            return None
        target = json.loads(body)["object"]
        while target["type"] == "tag":
            tag_body = self._get(f"/repos/{repository}/git/tags/{target['sha']}")
            if tag_body is None:
                raise ApiError(f"tag object {target['sha']} of {repository} is missing")
            target = json.loads(tag_body)["object"]
        return str(target["sha"])

    def compare(self, repository: str, base: str, head: str) -> str:
        """GitHub's comparison status of head against base: ahead, behind, identical or diverged."""
        path = f"/repos/{repository}/compare/{urllib.parse.quote(base)}...{urllib.parse.quote(head)}"
        body = self._get(path + "?per_page=1")
        if body is None:
            raise ApiError(f"cannot compare {base}...{head} in {repository}")
        return str(json.loads(body)["status"])

    def _get(self, path: str, accept: str = "application/vnd.github+json") -> bytes | None:
        request = urllib.request.Request(
            self._base + path,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "jade-vendor-freshness",
            },
        )
        try:
            with self._open(request, TIMEOUT_SECONDS) as response:  # type: ignore[attr-defined]
                return response.read()
        except urllib.error.HTTPError as error:
            error.close()
            if error.code == 404:
                return None
            raise ApiError(f"GET {path} answered HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise ApiError(f"GET {path} failed: {getattr(error, 'reason', error)}") from None
