"""An in-memory owner repository standing in for the GitHub API in tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

COMMIT_OLD = "a" * 40
COMMIT_NEW = "b" * 40


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FakeOwner:
    """Files per commit, tags, a newest release and comparison answers."""

    def __init__(self) -> None:
        self.files: dict[str, dict[str, bytes]] = {}
        self.tags: dict[str, str] = {}
        self.latest: str | None = None
        self.status = "behind"
        self.calls: list[str] = []

    def file_bytes(self, repository: str, path: str, ref: str) -> bytes | None:
        self.calls.append(f"file {ref} {path}")
        commit = self.tags.get(ref, ref)
        return self.files.get(commit, {}).get(path)

    def latest_release(self, repository: str) -> str | None:
        return self.latest

    def tag_commit(self, repository: str, tag: str) -> str | None:
        return self.tags.get(tag)

    def compare(self, repository: str, base: str, head: str) -> str:
        return self.status


def write_record(root: Path, name: str, record: dict) -> str:
    """Write `record` as JSON under `root` and return its relative path."""
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps(record), encoding="utf-8")
    return name


def record_for(data: bytes, *, ref: str | None = "v1.0.0", commit: str = COMMIT_OLD, **extra) -> dict:
    """A valid record for one file `tokens.css` vendored to `brand/tokens.css`."""
    return {
        "repository": "jade-the-cat/jade-brand",
        "ref": ref,
        "commit": commit,
        "files": [{"source": "tokens.css", "destination": "brand/tokens.css", "sha256": digest(data)}],
        **extra,
    }
