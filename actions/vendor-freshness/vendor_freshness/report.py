"""Findings as GitHub annotations, plain lines and a job summary table."""

from __future__ import annotations

from typing import Iterable, TextIO

from .checks import ERROR, NOTICE, WARNING, Finding

_SYMBOL = {ERROR: "✗", WARNING: "!", NOTICE: "·"}


def _escape(text: str) -> str:
    """Annotation data escaping (%, CR, LF), so a message cannot end the command early."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate(findings: Iterable[Finding], out: TextIO) -> None:
    """Write one `::level file=...::message` workflow command per finding."""
    for finding in findings:
        out.write(f"::{finding.level} file={_escape(finding.record)}::{_escape(finding.message)}\n")


def summary(records: list[str], findings: list[Finding], mode: str) -> str:
    """A Markdown job summary: each record's worst result, then every finding."""
    lines = [f"### Vendored copies ({mode})", "", "| Provenance | Result |", "|---|---|"]
    for record in records:
        levels = {f.level for f in findings if f.record == record}
        result = "✗ fails" if ERROR in levels else "! warns" if WARNING in levels else "✓ ok"
        lines.append(f"| `{record}` | {result} |")
    if findings:
        lines += ["", *(f"- {_SYMBOL[f.level]} `{f.record}`: {f.message}" for f in findings)]
    return "\n".join(lines) + "\n"


def exit_code(findings: Iterable[Finding]) -> int:
    return 1 if any(f.level == ERROR for f in findings) else 0

