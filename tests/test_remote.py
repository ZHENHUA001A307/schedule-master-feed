# -*- coding: utf-8 -*-
"""Remote tests. Run with RUN_REMOTE=1 to enable."""

import base64
import json
import os
import subprocess
import unittest
import urllib.error
import urllib.request

REPO = "ZHENHUA001A307/schedule-master-feed"
JSDELIVR = "https://cdn.jsdelivr.net/gh/" + REPO + "@main/feed.xml"


def gh(args, timeout=60):
    return subprocess.run(
        ["gh"] + args, capture_output=True, text=True, timeout=timeout
    )


def gh_available():
    try:
        return gh(["--version"]).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@unittest.skipUnless(
    os.environ.get("RUN_REMOTE") == "1",
    "set RUN_REMOTE=1 to enable remote tests",
)
class TestRemote(unittest.TestCase):
    def test_gh_available(self):
        self.assertTrue(gh_available())

    def test_workflow_active(self):
        r = gh(["workflow", "list", "--repo", REPO])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("routine-feed", r.stdout)
        self.assertIn("active", r.stdout)

    def test_recent_workflow_run(self):
        r = gh([
            "run", "list", "--repo", REPO,
            "--workflow", "feed.yml",
            "--limit", "1",
            "--json", "conclusion,status,createdAt",
        ])
        self.assertEqual(r.returncode, 0, r.stderr)
        runs = json.loads(r.stdout or "[]")
        self.assertTrue(len(runs) > 0, "no workflow run yet, trigger it first")
        self.assertEqual(runs[0]["conclusion"], "success", runs[0])

    def test_feed_via_github_api(self):
        r = gh(["api", "repos/" + REPO + "/contents/feed.xml"])
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        body = base64.b64decode(data["content"]).decode("utf-8")
        self.assertIn("<rss", body)
        self.assertIn("\u5185\u52a1\u63d0\u9192", body)
        self.assertIn("<item>", body)

    def test_jsdelivr_feed(self):
        try:
            with urllib.request.urlopen(JSDELIVR, timeout=30) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.skipTest("feed.xml not yet on jsdelivr")
            raise
        except (urllib.error.URLError, ConnectionResetError, OSError) as e:
            self.skipTest("jsdelivr unreachable (network): " + str(e))
        self.assertIn("<rss", body)
        self.assertIn("\u5185\u52a1\u63d0\u9192", body)


if __name__ == "__main__":
    unittest.main()
