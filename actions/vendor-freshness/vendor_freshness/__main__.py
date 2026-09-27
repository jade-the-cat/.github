"""Check vendored copies against their provenance records.

Usage:
    python3 -m vendor_freshness [--root DIR] [--local-only] [--today YYYY-MM-DD] RECORD...

RECORD paths are relative to --root (default: the working directory). Without
--local-only, GH_TOKEN (or GITHUB_TOKEN) must be able to read every source
repository. Exit status: 0 when nothing failed, 1 on any failure, 2 on bad usage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

from .checks import ERROR, Finding, check_fresh, check_local, check_source
from .github_api import ApiError, GitHubApi, SourceApi
from .provenance import ProvenanceError, load
from .report import annotate, exit_code, summary


def run(root: Path, records: list[str], api: SourceApi | None, today: dt.date) -> list[Finding]:
    """Every finding for every record; remote checks run only when `api` is given."""
    findings: list[Finding] = []
    for relative in records:
        try:
            record = load(root, relative)
        except ProvenanceError as error:
            findings += [Finding(ERROR, relative, problem) for problem in error.problems]
            continue
        findings += check_local(root, record)
        if api is None:
            continue
        try:
            findings += check_source(api, record)
            findings += check_fresh(api, record, today)
        except ApiError as error:
            findings.append(Finding(ERROR, relative, f"cannot reach {record.repository}: {error}"))
    return findings


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vendor_freshness", description=__doc__.split("\n\n")[0])
    parser.add_argument("records", nargs="+", help="provenance JSON files, relative to --root")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--local-only", action="store_true", help="skip the checks that read the owner")
    parser.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _arguments(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not args.local_only and not token:
        print("vendor_freshness: set GH_TOKEN, or pass --local-only", file=sys.stderr)
        return 2
    api = None if args.local_only else GitHubApi(token)
    findings = run(args.root, args.records, api, args.today)
    annotate(findings, sys.stdout)
    mode = "bytes only" if args.local_only else "bytes, source commit and newest release"
    report = summary(args.records, findings, mode)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(report)
    else:
        print(report)
    return exit_code(findings)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
