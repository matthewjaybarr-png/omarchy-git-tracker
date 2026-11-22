import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gitscan  # noqa: E402


class WebUrl(unittest.TestCase):
    def test_forms(self):
        cases = {
            "git@github.com:me/repo.git": "https://github.com/me/repo",
            "https://github.com/me/repo.git": "https://github.com/me/repo",
            "https://token@github.com/me/repo": "https://github.com/me/repo",
            "ssh://git@gitlab.com:22/grp/sub/repo.git": "https://gitlab.com/grp/sub/repo",
            "/mnt/backup/repo.git": "",
            "": "",
            "https://github.com/me/<img src=x>": "",
            "git@github.com:../../etc": "",
        }
        for remote, want in cases.items():
            self.assertEqual(gitscan.web_url(remote), want, remote)


class Status(unittest.TestCase):
    def test_parse(self):
        s = gitscan.parse_status(
            "# branch.oid abc\n# branch.head main\n# branch.upstream origin/main\n"
            "# branch.ab +2 -3\n1 M. N... 1 1 1 a b f1\n1 .M N... 1 1 1 a b f2\n"
            "1 MM N... 1 1 1 a b f3\nu UU N... 1 1 1 1 a b c f4\n? new\n? new2\n")
        self.assertEqual((s["branch"], s["upstream"], s["ahead"], s["behind"]), ("main", "origin/main", 2, 3))
        self.assertEqual((s["staged"], s["modified"], s["conflicts"], s["untracked"]), (2, 2, 1, 2))


class Scan(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            repo = os.path.join(d, "a", "proj")
            os.makedirs(os.path.join(d, ".hidden", "x", ".git"))
            os.makedirs(repo)
            run = lambda *a: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
            run("init", "-q", "-b", "main")
            run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "first")
            run("remote", "add", "origin", "git@github.com:me/proj.git")
            open(os.path.join(repo, "f"), "w").close()
            paths = gitscan.find_repos(d, 4)
            self.assertEqual(paths, [repo])
            self.assertEqual(gitscan.find_repos(d, 4, {os.path.join(d, "a")}), [])
            r = gitscan.inspect(repo, False)
            self.assertEqual((r["name"], r["branch"], r["untracked"], r["subject"]), ("proj", "main", 1, "first"))
            self.assertEqual(r["url"], "https://github.com/me/proj")
            self.assertTrue(r["hasRemote"])

    def test_repo_config_runs_nothing(self):
        """A copied-in repo's own config, filters and hooks must not run during a scan or fetch."""
        with tempfile.TemporaryDirectory() as d:
            repo, upstream, mark = os.path.join(d, "proj"), os.path.join(d, "up"), os.path.join(d, "RAN")
            run = lambda *a: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
            subprocess.run(["git", "init", "-q", "--bare", upstream], check=True)
            os.makedirs(repo)
            run("init", "-q", "-b", "main")
            with open(os.path.join(repo, "f"), "w") as f:
                f.write("a\n")
            run("add", "f")
            run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "first")
            run("remote", "add", "origin", upstream)
            run("push", "-q", "origin", "main")
            evil = "touch %s; false" % mark
            run("config", "core.fsmonitor", evil)
            run("config", "log.showSignature", "true")
            run("config", "gpg.program", evil)
            run("config", "filter.x.clean", evil)
            hook = os.path.join(repo, ".git", "hooks", "reference-transaction")
            with open(hook, "w") as f:
                f.write("#!/bin/sh\n%s\n" % evil)
            os.chmod(hook, 0o755)
            with open(os.path.join(repo, ".gitattributes"), "w") as f:
                f.write("f filter=x\n")
            with open(os.path.join(repo, "f"), "a") as f:
                f.write("b\n")
            r = gitscan.inspect(repo, True)
            self.assertFalse(os.path.exists(mark))
            self.assertEqual((r["modified"], r["error"]), (1, ""))
            self.assertIn("filter.x.clean=", gitscan.safe_opts(gitscan.local_keys(repo)))
            run("config", "credential.helper", evil)
            self.assertEqual(gitscan.inspect(repo, True)["error"], "fetch skipped: repo config")
            self.assertFalse(os.path.exists(mark))


if __name__ == "__main__":
    unittest.main()
