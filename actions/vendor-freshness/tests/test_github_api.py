import http.client
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vendor_freshness.github_api import ApiError, GitHubApi  # noqa: E402

TOKEN = "test-token-not-real"


class Recorder:
    """Answers requests from a {path-and-query: (status, body)} table and records them."""

    def __init__(self, answers):
        self.answers = answers
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        path = request.full_url.removeprefix("https://api.github.com")
        status, body = self.answers.get(path, (404, b"{}"))
        if status != 200:
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, io.BytesIO(body))
        return io.BytesIO(body)


def api(answers):
    recorder = Recorder(answers)
    return GitHubApi(TOKEN, opener=recorder, sleep=lambda attempt: None), recorder


class GitHubApiTests(unittest.TestCase):
    def test_reads_raw_file_bytes_at_a_ref(self):
        client, recorder = api({"/repos/o/r/contents/design-system/tokens.css?ref=abc": (200, b"bytes")})
        self.assertEqual(client.file_bytes("o/r", "design-system/tokens.css", "abc"), b"bytes")
        request = recorder.requests[0]
        self.assertEqual(request.get_header("Accept"), "application/vnd.github.raw+json")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")

    def test_a_missing_file_or_release_is_none(self):
        client, _ = api({})
        self.assertIsNone(client.file_bytes("o/r", "x", "abc"))
        self.assertIsNone(client.latest_release("o/r"))
        self.assertIsNone(client.tag_commit("o/r", "v1"))

    def test_follows_an_annotated_tag_to_its_commit(self):
        client, _ = api({
            "/repos/o/r/git/ref/tags/v1": (200, json.dumps({"object": {"type": "tag", "sha": "t1"}}).encode()),
            "/repos/o/r/git/tags/t1": (200, json.dumps({"object": {"type": "commit", "sha": "c1"}}).encode()),
        })
        self.assertEqual(client.tag_commit("o/r", "v1"), "c1")

    def test_reads_the_latest_release_and_a_comparison(self):
        client, _ = api({
            "/repos/o/r/releases/latest": (200, b'{"tag_name": "v0.2.2"}'),
            "/repos/o/r/compare/v0.2.2...abc?per_page=1": (200, b'{"status": "behind"}'),
        })
        self.assertEqual(client.latest_release("o/r"), "v0.2.2")
        self.assertEqual(client.compare("o/r", "v0.2.2", "abc"), "behind")

    def test_other_http_errors_raise_without_the_token(self):
        client, _ = api({"/repos/o/r/releases/latest": (401, b"{}")})
        with self.assertRaises(ApiError) as caught:
            client.latest_release("o/r")
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_an_unreachable_host_raises_after_three_tries(self):
        calls = []

        def offline(request, timeout):
            calls.append(request)
            raise urllib.error.URLError("no network")

        with self.assertRaises(ApiError) as caught:
            GitHubApi(TOKEN, opener=offline, sleep=lambda attempt: None).latest_release("o/r")
        self.assertEqual(len(calls), 3)
        self.assertIn("failed 3 times", str(caught.exception))

    def test_a_dropped_connection_or_a_5xx_is_retried(self):
        failures = [http.client.RemoteDisconnected("closed"), urllib.error.HTTPError("u", 502, "bad", {}, io.BytesIO())]

        def flaky(request, timeout):
            if failures:
                raise failures.pop(0)
            return io.BytesIO(b'{"tag_name": "v1"}')

        self.assertEqual(GitHubApi(TOKEN, opener=flaky, sleep=lambda attempt: None).latest_release("o/r"), "v1")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
