#!/usr/bin/env python3
"""Run one git action for the Git Tracker panel and print {"ok", "output"} as JSON.

Usage: gitaction.py commit PATH MESSAGE | push PATH | pull PATH | merge PATH BRANCH INTO | abort PATH
"""
import json
import os
import re
import subprocess
import sys

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/+-]+$")
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes",
       "GIT_EDITOR": "true", "GIT_MERGE_AUTOEDIT": "no"}


def git(path, *args, timeout=90):
    r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout, env=ENV)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def valid_branch(name):
    return bool(BRANCH_RE.match(name)) and not name.startswith("-") and ".." not in name


def run(action, path, arg="", into=""):
    if not os.path.isdir(os.path.join(path, ".git")) and not os.path.isfile(os.path.join(path, ".git")):
        return False, "not a git repository"
    if action == "commit":
        message = arg.strip()
        if not message:
            return False, "commit message is empty"
        ok, out = git(path, "add", "-A")
        if not ok:
            return ok, out
        return git(path, "commit", "-m", message)
    if action == "push":
        ok, upstream = git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if ok:
            return git(path, "push")
        ok, branch = git(path, "symbolic-ref", "--short", "HEAD")
        if not ok:
            return False, "detached HEAD: check out a branch first"
        ok, remotes = git(path, "remote")
        remote = "origin" if "origin" in remotes.split() else (remotes.split() or [""])[0]
        if not remote:
            return False, "no remote to push to"
        return git(path, "push", "-u", remote, branch)
    if action == "pull":
        return git(path, "pull", "--no-edit")
    if action == "merge":
        if not valid_branch(arg) or not valid_branch(into):
            return False, "invalid branch name"
        # The user confirmed "merge arg into <into>"; refuse if another tool switched branches since.
        ok, current = git(path, "symbolic-ref", "--short", "HEAD")
        if not ok or current != into:
            return False, "the checked-out branch is now %s, not %s. Refresh and try again." % (
                current if ok else "detached HEAD", into)
        return git(path, "merge", "--no-edit", arg)
    if action == "abort":
        return git(path, "merge", "--abort")
    return False, "unknown action"


HINTS = [
    (("Permission denied (publickey)", "Host key verification failed"),
     "Hint: your SSH key isn't set up for this host. Add it with ssh-add or switch the remote to https."),
    (("could not read Username", "Authentication failed", "terminal prompts disabled"),
     "Hint: this remote needs a login. Set up a git credential helper (e.g. `gh auth setup-git`) or an SSH key."),
    (("[rejected]", "fetch first", "non-fast-forward"),
     "Hint: the remote has commits you don't have yet. Pull first, then push."),
    (("Need to specify how to reconcile", "Not possible to fast-forward"),
     "Hint: your branch and the remote have both moved. Set `git config pull.rebase false` to merge, or pull in a terminal."),
    (("CONFLICT", "Automatic merge failed"),
     "Hint: fix the conflicted files, then commit from here, or press Abort merge."),
    (("Please tell me who you are",),
     "Hint: set your name and email with `git config --global user.name` and `user.email`."),
]


def with_hint(output):
    for needles, hint in HINTS:
        if any(n in output for n in needles):
            return output + "\n" + hint
    return output


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"ok": False, "output": __doc__.strip()}))
        return 2
    try:
        ok, out = run(argv[0], os.path.abspath(argv[1]), *argv[2:4])
    except subprocess.TimeoutExpired:
        ok, out = False, "timed out"
    out = out[-1200:] if ok else with_hint(out[-1200:])
    print(json.dumps({"ok": ok, "output": out}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
