"""The provenance record every Jade repository keeps next to a vendored copy.

One format for every vendored copy (tokens, logos, the twin rig, API
schemas), so one check can hold all of them to their owner:

    {
      "about": "optional note for readers",
      "repository": "jade-the-cat/jade-brand",
      "ref": "v0.2.2",
      "commit": "<40-hex commit the files were copied from>",
      "files": [
        {"source": "design-system/tokens.css",
         "destination": "brand/tokens.css",
         "sha256": "<64-hex SHA-256 of the vendored bytes>"}
      ],
      "pin": {"reason": "why this copy stays behind", "until": "2026-10-12"}
    }

`ref` is the owner's release tag the commit carries, or null for an untagged
commit. `destination` is relative to the consumer repository's root, `source`
to the owner's. `pin` is optional: an intentional, dated exception that lets
the copy stay behind the owner's newest release until `until` (inclusive).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*)/[A-Za-z0-9._-]+$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {"about", "repository", "ref", "commit", "files", "pin"}
_FILE_KEYS = {"source", "destination", "sha256"}
_PIN_KEYS = {"reason", "until"}


class ProvenanceError(Exception):
    """A provenance record that cannot be read, with every problem found in it."""

    def __init__(self, path: str, problems: list[str]) -> None:
        super().__init__(f"{path}: " + "; ".join(problems))
        self.path = path
        self.problems = problems


@dataclass(frozen=True)
class VendoredFile:
    """One copied file: where it came from, where it lives here, and its bytes' hash."""

    source: str
    destination: str
    sha256: str


@dataclass(frozen=True)
class Pin:
    """An intentional, dated exception to "the copy follows the newest release"."""

    reason: str
    until: dt.date


@dataclass(frozen=True)
class Provenance:
    """A parsed record. `path` is the record's own path, relative to the repository root."""

    path: str
    repository: str
    ref: str | None
    commit: str
    files: tuple[VendoredFile, ...]
    pin: Pin | None

    @property
    def owner(self) -> str:
        return self.repository.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.repository.split("/", 1)[1]


def load(root: Path, relative: str) -> Provenance:
    """Read and validate the record at `root / relative`."""
    try:
        data = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProvenanceError(relative, [f"cannot read it as JSON ({error})"]) from error
    return parse(data, relative)


def parse(data: object, path: str) -> Provenance:
    """Validate a decoded record, collecting every problem before failing."""
    if not isinstance(data, dict):
        raise ProvenanceError(path, ["the record must be a JSON object"])
    problems = [f"unknown key {key!r}" for key in sorted(set(data) - _KEYS)]
    repository = _text(data, "repository", problems, pattern=_REPOSITORY, what="owner/name")
    commit = _text(data, "commit", problems, pattern=_COMMIT, what="a 40-hex commit")
    ref = data.get("ref")
    if ref is not None and (not isinstance(ref, str) or not ref.strip()):
        problems.append("ref must be a tag name or null")
    files = _files(data.get("files"), problems)
    pin = _pin(data.get("pin"), problems)
    if problems:
        raise ProvenanceError(path, problems)
    return Provenance(path, repository, ref, commit, files, pin)


def _text(data: dict, key: str, problems: list[str], *, pattern: re.Pattern[str], what: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not pattern.match(value):
        problems.append(f"{key} must be {what}, not {value!r}")
        return ""
    return value


def _files(raw: object, problems: list[str]) -> tuple[VendoredFile, ...]:
    if not isinstance(raw, list) or not raw:
        problems.append("files must be a non-empty list")
        return ()
    files = []
    for index, entry in enumerate(raw):
        where = f"files[{index}]"
        if not isinstance(entry, dict) or set(entry) != _FILE_KEYS:
            problems.append(f"{where} must have exactly source, destination and sha256")
            continue
        for key in ("source", "destination"):
            if not _is_relative_path(entry[key]):
                problems.append(f"{where}.{key} must be a relative path inside the repository")
        if not isinstance(entry["sha256"], str) or not _SHA256.match(entry["sha256"]):
            problems.append(f"{where}.sha256 must be 64 lowercase hex characters")
        files.append(VendoredFile(str(entry["source"]), str(entry["destination"]), str(entry["sha256"])))
    destinations = [f.destination for f in files]
    problems.extend(f"{d} is listed twice" for d in sorted({d for d in destinations if destinations.count(d) > 1}))
    return tuple(files)


def _pin(raw: object, problems: list[str]) -> Pin | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != _PIN_KEYS:
        problems.append("pin must have exactly reason and until")
        return None
    reason, until = raw["reason"], raw["until"]
    if not isinstance(reason, str) or not reason.strip():
        problems.append("pin.reason must say why the copy stays behind")
    try:
        date = dt.date.fromisoformat(until) if isinstance(until, str) else None
    except ValueError:
        date = None
    if date is None:
        problems.append(f"pin.until must be an ISO date (YYYY-MM-DD), not {until!r}")
        return None
    return Pin(str(reason), date)


def _is_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts
