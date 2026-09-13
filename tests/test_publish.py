"""Publishing integration tests using local Git repositories (no network)."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import publish


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.remote = self.base / "remote.git"
        self.source = self.base / "source"
        self.git(self.base, "init", "--bare", str(self.remote))
        self.git(self.base, "init", str(self.source))
        self.git(self.source, "checkout", "-b", "main")
        self.git(self.source, "config", "user.name", "Test Publisher")
        self.git(self.source, "config", "user.email", "publisher@example.invalid")
        self.old_name = "ofertas_2026-09-10_1747.html"
        archived = self.source / "site" / "reports" / self.old_name
        archived.parent.mkdir(parents=True)
        archived.write_text("<html><body>old report</body></html>")
        (self.source / "README.md").write_text("original\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "initial")
        self.git(self.source, "remote", "add", "origin", str(self.remote))
        self.git(self.source, "push", "-u", "origin", "main")
        self.reports = self.source / "data" / "reports"
        self.reports.mkdir(parents=True)
        self.new_name = "ofertas_2026-09-13_0900.html"
        (self.reports / self.new_name).write_text("<html><body>new report</body></html>")
        for name, value in (("ROOT", self.source), ("REPORTS_DIR", self.reports)):
            patcher = patch.object(publish, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        ).stdout.strip()

    def remote_file(self, path):
        return self.git(self.remote, "show", f"main:{path}")

    def test_preserves_history_and_leaves_local_work_untouched(self):
        (self.source / "README.md").write_text("unpublished local commit\n")
        self.git(self.source, "add", "README.md")
        self.git(self.source, "commit", "-m", "local only")
        (self.source / "README.md").write_text("staged work\n")
        self.git(self.source, "add", "README.md")
        before = self.git(self.source, "status", "--porcelain")
        head = self.git(self.source, "rev-parse", "HEAD")
        publish.push()
        self.assertIn("old report", self.remote_file(f"site/reports/{self.old_name}"))
        self.assertIn("new report", self.remote_file("site/index.html"))
        self.assertIn(self.old_name, self.remote_file("site/reports/index.html"))
        self.assertEqual("original", self.remote_file("README.md"))
        self.assertEqual(head, self.git(self.source, "rev-parse", "HEAD"))
        self.assertEqual(before, self.git(self.source, "status", "--porcelain"))

    def test_repeated_publish_does_not_create_duplicate_commit(self):
        publish.push()
        first = self.git(self.remote, "rev-parse", "main")
        publish.push()
        self.assertEqual(first, self.git(self.remote, "rev-parse", "main"))

    def test_failed_push_can_retry_without_rescraping(self):
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        with self.assertRaises(RuntimeError):
            publish.push()
        hook.unlink()
        publish.push()
        self.assertIn("new report", self.remote_file("site/index.html"))

    def test_remote_newer_report_remains_latest(self):
        newer = "ofertas_2026-09-14_0900.html"
        (self.source / "site" / "reports" / newer).write_text("<body>newest</body>")
        self.git(self.source, "add", "site")
        self.git(self.source, "commit", "-m", "newer report")
        self.git(self.source, "push")
        publish.push()
        self.assertIn("newest", self.remote_file("site/index.html"))


if __name__ == "__main__":
    unittest.main()
