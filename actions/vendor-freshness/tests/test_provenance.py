import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vendor_freshness.provenance import ProvenanceError, parse  # noqa: E402

GOOD = {
    "about": "a note",
    "repository": "jade-the-cat/jade-brand",
    "ref": "v0.2.2",
    "commit": "45c7e2324df8b00448073f84140f1ec6e6952b91",
    "files": [{"source": "design-system/tokens.css", "destination": "brand/tokens.css", "sha256": "0" * 64}],
}


class ParseTests(unittest.TestCase):
    def test_reads_a_complete_record(self):
        record = parse(GOOD, "brand/provenance.json")
        self.assertEqual(record.owner, "jade-the-cat")
        self.assertEqual(record.name, "jade-brand")
        self.assertEqual(record.ref, "v0.2.2")
        self.assertEqual(record.files[0].destination, "brand/tokens.css")
        self.assertIsNone(record.pin)

    def test_accepts_an_untagged_commit_and_a_dated_pin(self):
        record = parse({**GOOD, "ref": None, "pin": {"reason": "needs Swift work", "until": "2026-10-12"}}, "p")
        self.assertIsNone(record.ref)
        self.assertEqual(record.pin.until, dt.date(2026, 10, 12))

    def test_collects_every_problem_at_once(self):
        bad = {
            "repository": "no-slash",
            "commit": "abc",
            "ref": "",
            "files": [{"source": "../escape", "destination": "/abs", "sha256": "XYZ"}],
            "pinned": True,
        }
        with self.assertRaises(ProvenanceError) as caught:
            parse(bad, "p.json")
        problems = caught.exception.problems
        self.assertIn("unknown key 'pinned'", problems)
        self.assertTrue(any(p.startswith("repository must be") for p in problems))
        self.assertTrue(any(p.startswith("commit must be") for p in problems))
        self.assertIn("ref must be a tag name or null", problems)
        self.assertIn("files[0].source must be a relative path inside the repository", problems)
        self.assertIn("files[0].destination must be a relative path inside the repository", problems)
        self.assertIn("files[0].sha256 must be 64 lowercase hex characters", problems)

    def test_rejects_an_empty_file_list_and_duplicate_destinations(self):
        with self.assertRaises(ProvenanceError) as empty:
            parse({**GOOD, "files": []}, "p")
        self.assertIn("files must be a non-empty list", empty.exception.problems)
        twice = [GOOD["files"][0], {**GOOD["files"][0], "source": "other.css"}]
        with self.assertRaises(ProvenanceError) as duplicate:
            parse({**GOOD, "files": twice}, "p")
        self.assertIn("brand/tokens.css is listed twice", duplicate.exception.problems)

    def test_a_pin_needs_a_reason_and_a_real_date(self):
        for pin, expected in (
            ({"reason": "", "until": "2026-10-12"}, "pin.reason must say why the copy stays behind"),
            ({"reason": "x", "until": "next week"}, "pin.until must be an ISO date (YYYY-MM-DD), not 'next week'"),
            ({"reason": "x"}, "pin must have exactly reason and until"),
        ):
            with self.subTest(pin=pin), self.assertRaises(ProvenanceError) as caught:
                parse({**GOOD, "pin": pin}, "p")
            self.assertIn(expected, caught.exception.problems)

    def test_rejects_a_record_that_is_not_an_object(self):
        with self.assertRaises(ProvenanceError):
            parse([GOOD], "p")


if __name__ == "__main__":
    unittest.main()
