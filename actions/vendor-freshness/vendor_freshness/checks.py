"""The three promises a vendored copy makes, checked against its provenance record.

1. local  — the committed bytes are the bytes the record lists (nobody edited the copy);
2. source — those bytes are what the owner holds at the recorded commit (and the recorded
            ref names that commit), so the record is true;
3. fresh  — the owner's newest release holds the same bytes, unless a dated pin says the
            copy stays behind on purpose.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .github_api import SourceApi
from .provenance import Provenance

ERROR, WARNING, NOTICE = "error", "warning", "notice"


@dataclass(frozen=True)
class Finding:
    """One result line, at a GitHub annotation level, about one provenance record."""

    level: str
    record: str
    message: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_local(root: Path, record: Provenance) -> list[Finding]:
    """Every vendored file exists and hashes to what the record says."""
    findings = []
    for file in record.files:
        path = root / file.destination
        if not path.is_file():
            findings.append(Finding(ERROR, record.path, f"{file.destination} is missing"))
        elif sha256(path.read_bytes()) != file.sha256:
            findings.append(Finding(
                ERROR, record.path,
                f"{file.destination} is not the recorded copy of {record.repository}:{file.source}; "
                "never edit a vendored file, re-run the sync instead",
            ))
    return findings


def check_source(api: SourceApi, record: Provenance) -> list[Finding]:
    """The recorded hashes are the owner's bytes at the recorded commit and ref."""
    findings = []
    if record.ref is not None:
        tagged = api.tag_commit(record.repository, record.ref)
        if tagged != record.commit:
            findings.append(Finding(
                ERROR, record.path,
                f"ref {record.ref} of {record.repository} is {tagged or 'missing'}, "
                f"but the record says it is {record.commit}",
            ))
    for file in record.files:
        data = api.file_bytes(record.repository, file.source, record.commit)
        if data is None:
            findings.append(Finding(
                ERROR, record.path,
                f"{record.repository}@{record.commit[:12]} has no {file.source} "
                "(or the token cannot read that repository)",
            ))
        elif sha256(data) != file.sha256:
            findings.append(Finding(
                ERROR, record.path,
                f"{file.destination}: the recorded sha256 is not {record.repository}:{file.source} "
                f"at {record.commit[:12]}; the record was edited by hand",
            ))
    return findings


def changed_at(api: SourceApi, record: Provenance, ref: str) -> list[str]:
    """The sources whose bytes at `ref` differ from the vendored copy (missing counts)."""
    changed = []
    for file in record.files:
        data = api.file_bytes(record.repository, file.source, ref)
        if data is None or sha256(data) != file.sha256:
            changed.append(file.source)
    return changed


def check_fresh(api: SourceApi, record: Provenance, today: dt.date) -> list[Finding]:
    """The copy matches the owner's newest release, or a live pin explains why not."""
    findings, stale = _freshness(api, record, today)
    if record.pin is not None and not stale:
        findings.append(Finding(
            WARNING, record.path,
            f"the copy is current, so the pin (until {record.pin.until.isoformat()}) is no longer needed; remove it",
        ))
    return findings


def _freshness(api: SourceApi, record: Provenance, today: dt.date) -> tuple[list[Finding], bool]:
    """The freshness findings, and whether the copy is behind the newest release."""
    latest = api.latest_release(record.repository)
    if latest is None:
        return [Finding(NOTICE, record.path, f"{record.repository} has no release yet; nothing to compare")], False
    if latest == record.ref:
        return [], False
    changed = changed_at(api, record, latest)
    if not changed:
        return [Finding(
            NOTICE, record.path,
            f"recorded {record.ref or record.commit[:12]}, newest release {latest}: "
            "the vendored files are unchanged there; the next sync records it",
        )], False
    status = api.compare(record.repository, latest, record.commit)
    if status == "ahead":
        return [Finding(
            WARNING, record.path,
            f"vendored from {record.commit[:12]}, which is newer than {record.repository}'s newest "
            f"release {latest}; vendor released files once the owner releases",
        )], False
    return _stale(record, latest, changed, today), True


def _stale(record: Provenance, latest: str, changed: list[str], today: dt.date) -> list[Finding]:
    listed = ", ".join(changed[:5]) + (f" and {len(changed) - 5} more" if len(changed) > 5 else "")
    behind = (
        f"behind {record.repository} {latest} (recorded {record.ref or record.commit[:12]}); "
        f"changed there: {listed}"
    )
    if record.pin is None:
        return [Finding(ERROR, record.path, f"{behind}. Re-vendor, or add a dated pin with the reason")]
    if today <= record.pin.until:
        return [Finding(
            WARNING, record.path,
            f"{behind}. Pinned until {record.pin.until.isoformat()}: {record.pin.reason}",
        )]
    return [Finding(
        ERROR, record.path,
        f"{behind}. The pin expired on {record.pin.until.isoformat()} ({record.pin.reason}); "
        "re-vendor, or renew the pin with a new date and reason",
    )]
