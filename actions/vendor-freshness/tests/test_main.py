import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import record_for, write_record  # noqa: E402

from vendor_freshness.__main__ import main  # noqa: E402
from vendor_freshness.checks import Finding  # noqa: E402
from vendor_freshness.report import annotate, summary  # noqa: E402


class MainTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "brand").mkdir()
        (self.root / "brand/tokens.css").write_bytes(b"x\n")

    def invoke(self, *args, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_local_only_passes_a_true_copy_and_writes_the_summary(self):
        write_record(self.root, "brand/provenance.json", record_for(b"x\n"))
        summary_file = self.root / "summary.md"
        code, out, _ = self.invoke("--local-only", "brand/provenance.json",
                                   env={"GITHUB_STEP_SUMMARY": str(summary_file)})
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("| `brand/provenance.json` | ✓ ok |", summary_file.read_text())

    def test_an_edited_copy_exits_1_with_an_annotation(self):
        write_record(self.root, "brand/provenance.json", record_for(b"other\n"))
        code, out, _ = self.invoke("--local-only", "brand/provenance.json")
        self.assertEqual(code, 1)
        self.assertIn("::error file=brand/provenance.json::", out)

    def test_remote_checks_need_a_token(self):
        write_record(self.root, "brand/provenance.json", record_for(b"x\n"))
        code, _, err = self.invoke("brand/provenance.json")
        self.assertEqual(code, 2)
        self.assertIn("set GH_TOKEN", err)


class ReportTests(unittest.TestCase):
    def test_annotations_escape_newlines_and_percent(self):
        out = io.StringIO()
        annotate([Finding("warning", "p.json", "50%\nsecond line")], out)
        self.assertEqual(out.getvalue(), "::warning file=p.json::50%25%0Asecond line\n")

    def test_summary_shows_the_worst_result_per_record(self):
        findings = [Finding("warning", "a.json", "w"), Finding("error", "b.json", "e")]
        text = summary(["a.json", "b.json", "c.json"], findings, "mode")
        self.assertIn("| `a.json` | ! warns |", text)
        self.assertIn("| `b.json` | ✗ fails |", text)
        self.assertIn("| `c.json` | ✓ ok |", text)


if __name__ == "__main__":
    unittest.main()
