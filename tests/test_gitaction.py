import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gitaction  # noqa: E402
import gitscan  # noqa: E402

ID = ["-c", "user.name=t", "-c", "user.email=t@t"]


def sh(path, *args):
    subprocess.run(["git", "-C", path, *args], check=True, capture_output=True)


class Actions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.origin, self.repo = os.path.join(d, "origin.git"), os.path.join(d, "work")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, self.repo], check=True, capture_output=True)
        sh(self.repo, "config", "user.name", "t")
        sh(self.repo, "config", "user.email", "t@t")
        sh(self.repo, "checkout", "-q", "-b", "main")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text="x"):
        with open(os.path.join(self.repo, name), "w") as f:
            f.write(text)

    def test_commit_push_pull_merge(self):
        self.assertEqual(gitaction.run("commit", self.repo, "  ")[0], False)
        self.write("a")
        ok, out = gitaction.run("commit", self.repo, "first")
        self.assertTrue(ok, out)
        # No upstream yet: push sets it.
        ok, out = gitaction.run("push", self.repo)
        self.assertTrue(ok, out)
        self.assertEqual(gitscan.inspect(self.repo, False)["upstream"], "origin/main")
        # Someone else pushes; pull brings it in.
        other = os.path.join(self.tmp.name, "other")
        subprocess.run(["git", "clone", "-q", self.origin, other], check=True, capture_output=True)
        open(os.path.join(other, "b"), "w").close()
        sh(other, "add", "b")
        sh(other, *ID, "commit", "-q", "-m", "second")
        sh(other, "push", "-q")
        ok, out = gitaction.run("pull", self.repo)
        self.assertTrue(ok, out)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "b")))
        # Merge a feature branch.
        sh(self.repo, "checkout", "-q", "-b", "feature")
        self.write("c")
        gitaction.run("commit", self.repo, "feature work")
        sh(self.repo, "checkout", "-q", "main")
        self.assertIn("feature", gitscan.inspect(self.repo, False)["branches"])
        ok, out = gitaction.run("merge", self.repo, "feature", "main")
        self.assertTrue(ok, out)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "c")))

    def test_conflict_then_abort(self):
        self.write("a", "base")
        gitaction.run("commit", self.repo, "base")
        sh(self.repo, "checkout", "-q", "-b", "side")
        self.write("a", "side")
        gitaction.run("commit", self.repo, "side")
        sh(self.repo, "checkout", "-q", "main")
        self.write("a", "main")
        gitaction.run("commit", self.repo, "main")
        ok, _ = gitaction.run("merge", self.repo, "side", "main")
        self.assertFalse(ok)
        state = gitscan.inspect(self.repo, False)
        self.assertTrue(state["merging"])
        self.assertEqual(state["conflicts"], 1)
        ok, out = gitaction.run("abort", self.repo)
        self.assertTrue(ok, out)
        self.assertFalse(gitscan.inspect(self.repo, False)["merging"])

    def test_rejects_option_shaped_branch(self):
        self.write("a")
        gitaction.run("commit", self.repo, "first")
        for bad in ["--abort", "a..b", "x;rm", ""]:
            self.assertEqual(gitaction.run("merge", self.repo, bad, "main"), (False, "invalid branch name"))

    def test_merge_refuses_if_branch_changed(self):
        self.write("a")
        gitaction.run("commit", self.repo, "first")
        sh(self.repo, "branch", "feature")
        sh(self.repo, "checkout", "-q", "-b", "other")
        ok, out = gitaction.run("merge", self.repo, "feature", "main")
        self.assertFalse(ok)
        self.assertIn("now other", out)


if __name__ == "__main__":
    unittest.main()
