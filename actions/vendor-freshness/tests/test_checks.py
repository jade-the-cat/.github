import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import COMMIT_NEW, COMMIT_OLD, FakeOwner, record_for, write_record  # noqa: E402

from vendor_freshness.__main__ import run  # noqa: E402

OLD, NEW = b":root { --a: 1; }\n", b":root { --a: 2; }\n"
TODAY = dt.date(2026, 9, 28)


class CheckTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "brand").mkdir()
        (self.root / "brand/tokens.css").write_bytes(OLD)
        self.owner = FakeOwner()
        self.owner.files = {COMMIT_OLD: {"tokens.css": OLD}, COMMIT_NEW: {"tokens.css": NEW}}
        self.owner.tags = {"v1.0.0": COMMIT_OLD, "v1.1.0": COMMIT_NEW}
        self.owner.latest = "v1.0.0"

    def check(self, record: dict, *, api=True, today=TODAY):
        name = write_record(self.root, "brand/provenance.json", record)
        return run(self.root, [name], self.owner if api else None, today)

    def levels(self, findings):
        return [f.level for f in findings]


class LocalAndSourceTests(CheckTestCase):
    def test_a_current_copy_passes_every_check(self):
        self.assertEqual(self.check(record_for(OLD)), [])

    def test_an_edited_copy_fails_even_without_a_token(self):
        (self.root / "brand/tokens.css").write_bytes(b"edited\n")
        findings = self.check(record_for(OLD), api=False)
        self.assertEqual(self.levels(findings), ["error"])
        self.assertIn("never edit a vendored file", findings[0].message)

    def test_a_missing_copy_fails(self):
        (self.root / "brand/tokens.css").unlink()
        self.assertIn("brand/tokens.css is missing", [f.message for f in self.check(record_for(OLD))])

    def test_a_hash_the_owner_never_had_fails(self):
        (self.root / "brand/tokens.css").write_bytes(b"hand-made\n")
        record = record_for(b"hand-made\n")
        findings = self.check(record)
        self.assertEqual(self.levels(findings), ["error"])
        self.assertIn("the record was edited by hand", findings[0].message)

    def test_a_ref_that_names_another_commit_fails(self):
        findings = self.check(record_for(OLD, ref="v1.1.0"))
        self.assertIn("ref v1.1.0 of jade-the-cat/jade-brand is " + COMMIT_NEW, findings[0].message)

    def test_a_source_the_owner_lacks_fails(self):
        self.owner.files[COMMIT_OLD] = {}
        messages = [f.message for f in self.check(record_for(OLD))]
        self.assertTrue(any("has no tokens.css" in m for m in messages))

    def test_a_malformed_record_is_reported_not_raised(self):
        findings = self.check({"repository": "x"})
        self.assertTrue(findings)
        self.assertEqual(set(self.levels(findings)), {"error"})


class FreshnessTests(CheckTestCase):
    def test_behind_the_newest_release_fails(self):
        self.owner.latest = "v1.1.0"
        findings = self.check(record_for(OLD))
        self.assertEqual(self.levels(findings), ["error"])
        self.assertIn("behind jade-the-cat/jade-brand v1.1.0", findings[0].message)
        self.assertIn("changed there: tokens.css", findings[0].message)

    def test_a_live_pin_turns_staleness_into_a_warning(self):
        self.owner.latest = "v1.1.0"
        pin = {"reason": "the generator needs Swift work", "until": "2026-10-12"}
        findings = self.check(record_for(OLD, pin=pin))
        self.assertEqual(self.levels(findings), ["warning"])
        self.assertIn("Pinned until 2026-10-12: the generator needs Swift work", findings[0].message)

    def test_the_pin_holds_through_its_last_day_and_fails_after(self):
        self.owner.latest = "v1.1.0"
        pin = {"reason": "wait", "until": "2026-10-12"}
        self.assertEqual(self.levels(self.check(record_for(OLD, pin=pin), today=dt.date(2026, 10, 12))), ["warning"])
        expired = self.check(record_for(OLD, pin=pin), today=dt.date(2026, 10, 13))
        self.assertEqual(self.levels(expired), ["error"])
        self.assertIn("The pin expired on 2026-10-12", expired[0].message)

    def test_a_newer_release_with_the_same_bytes_is_only_a_notice(self):
        self.owner.files[COMMIT_NEW] = {"tokens.css": OLD}
        self.owner.latest = "v1.1.0"
        findings = self.check(record_for(OLD))
        self.assertEqual(self.levels(findings), ["notice"])
        self.assertIn("unchanged there", findings[0].message)

    def test_a_copy_newer_than_the_newest_release_warns(self):
        self.owner.latest = "v1.1.0"
        self.owner.status = "ahead"
        self.assertEqual(self.levels(self.check(record_for(OLD))), ["warning"])

    def test_an_owner_without_releases_is_a_notice(self):
        self.owner.latest = None
        self.assertEqual(self.levels(self.check(record_for(OLD))), ["notice"])

    def test_an_untagged_commit_behind_the_release_fails(self):
        self.owner.latest = "v1.1.0"
        findings = self.check(record_for(OLD, ref=None))
        self.assertEqual(self.levels(findings), ["error"])
        self.assertIn(f"recorded {COMMIT_OLD[:12]}", findings[0].message)

    def test_a_pin_on_a_current_copy_asks_to_be_removed(self):
        findings = self.check(record_for(OLD, pin={"reason": "old", "until": "2026-10-12"}))
        self.assertEqual(self.levels(findings), ["warning"])
        self.assertIn("no longer needed; remove it", findings[0].message)

    def test_local_only_mode_never_reads_the_owner(self):
        self.owner.latest = "v1.1.0"
        self.assertEqual(self.check(record_for(OLD), api=False), [])
        self.assertEqual(self.owner.calls, [])


if __name__ == "__main__":
    unittest.main()
