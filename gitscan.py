#!/usr/bin/env python3
"""Find local git repos and print their state as JSON for the Git Tracker panel.

Usage: gitscan.py [--fetch] [--depth N] [--exclude PATH]... ROOT...
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

SKIP_DIRS = {"node_modules", "venv", "__pycache__", "target", "build", "dist"}
MAX_REPOS = 400
MAX_TEXT = 200
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(:\d+)?$")
PATH_RE = re.compile(r"^[A-Za-z0-9._~/-]+$")


def clip(value, limit=MAX_TEXT):
    value = str(value or "").replace("\n", " ").strip()
    return value[:limit]


def find_repos(root, depth, exclude=()):
    """Walk root up to depth levels; stop descending at a repo, skip hidden and excluded dirs."""
    found = []
    # shortcut: nested repos inside a repo (vendored clones) are not listed; add a flag if wanted.
    stack = [(root, 0)]
    while stack and len(found) < MAX_REPOS:
        path, level = stack.pop()
        if path in exclude:
            continue
        try:
            entries = list(os.scandir(path))
        except OSError:
            continue
        if any(e.name == ".git" for e in entries):
            found.append(path)
            continue
        if level >= depth:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False) and not e.name.startswith(".") and e.name not in SKIP_DIRS:
                    stack.append((e.path, level + 1))
            except OSError:
                pass
    return found


def web_url(remote):
    """Turn a git remote into a browsable https URL, or "" if it isn't one."""
    remote = (remote or "").strip()
    m = re.match(r"^(?:ssh://)?[\w.-]+@([^:/]+)[:/](.+)$", remote) or re.match(
        r"^https?://(?:[^@/]+@)?([^/]+)/(.+)$", remote)
    if not m:
        return ""
    host, path = m.group(1), m.group(2)
    if path.endswith(".git"):
        path = path[:-4]
    if remote.startswith("ssh://"):
        path = re.sub(r"^\d+/", "", path)  # ssh://git@host:22/owner/repo — the port is not part of the web path
    path = path.strip("/")
    if not HOST_RE.match(host) or not path or not PATH_RE.match(path) or ".." in path:
        return ""
    return "https://%s/%s" % (host, path)


def parse_status(text):
    """Parse `git status --porcelain=v2 --branch` output."""
    s = {"branch": "", "upstream": "", "ahead": 0, "behind": 0,
         "staged": 0, "modified": 0, "untracked": 0, "conflicts": 0}
    for line in text.splitlines():
        if line.startswith("# branch.head "):
            s["branch"] = clip(line[14:], 80)
        elif line.startswith("# branch.upstream "):
            s["upstream"] = clip(line[18:], 120)
        elif line.startswith("# branch.ab "):
            parts = line.split()
            s["ahead"], s["behind"] = abs(int(parts[2])), abs(int(parts[3]))
        elif line.startswith(("1 ", "2 ")):
            xy = line[2:4]
            if xy[0] != ".":
                s["staged"] += 1
            if xy[1] != ".":
                s["modified"] += 1
        elif line.startswith("u "):
            s["conflicts"] += 1
        elif line.startswith("? "):
            s["untracked"] += 1
    return s


# Local repo config can name programs that git runs on its own. A downloaded or restored
# working copy is not trusted, so automatic scans switch those off and never run hooks.
SAFE_OPTS = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
             "-c", "log.showSignature=false"]
# Local keys that make `git fetch` run a program (env GIT_SSH_COMMAND already overrides core.sshCommand).
FETCH_RISK_RE = re.compile(r"^(core\.gitproxy|core\.askpass|credential\..*|remote\..*\.(uploadpack|receivepack)"
                           r"|protocol\..*|url\..*)$")
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_ASKPASS": "",
       "SSH_ASKPASS": "", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def local_keys(path):
    """Keys set by the repo's own config (local and worktree scope). Reading config runs nothing."""
    r = subprocess.run(["git", "-C", path, "config", "--list", "--show-scope", "-z"],
                       capture_output=True, text=True, timeout=15, env=ENV)
    parts = r.stdout.split("\0")  # scope NUL key LF value NUL ...
    return [entry.split("\n", 1)[0].lower() for scope, entry in zip(parts[::2], parts[1::2])
            if scope in ("local", "worktree")]


def safe_opts(keys):
    """SAFE_OPTS plus switching off every filter driver the repo defines for itself."""
    opts = list(SAFE_OPTS)
    names = {k[len("filter."):k.rindex(".")] for k in keys if k.startswith("filter.") and k.count(".") >= 2}
    for name in sorted(names):
        for part in ("clean", "smudge", "process"):
            opts += ["-c", "filter.%s.%s=" % (name, part)]
        opts += ["-c", "filter.%s.required=false" % name]
    return opts


def git(path, opts, *args, timeout=15):
    r = subprocess.run(["git", *opts, "-C", path, *args], capture_output=True, text=True,
                       timeout=timeout, env=ENV)
    return r.stdout if r.returncode == 0 else ""


def inspect(path, fetch):
    home = os.path.expanduser("~")
    repo = {"name": clip(os.path.basename(path), 80), "path": path,
            "displayPath": clip("~" + path[len(home):] if path.startswith(home) else path),
            "error": ""}
    try:
        fetchFailed = False
        keys = local_keys(path)
        opts = safe_opts(keys)
        if fetch:
            if any(FETCH_RISK_RE.match(k) for k in keys):
                fetchFailed = "fetch skipped: repo config"
            elif subprocess.run(["git", *opts, "-C", path, "fetch", "--quiet", "--prune", "--no-recurse-submodules"],
                                capture_output=True, timeout=30, env=ENV).returncode != 0:
                fetchFailed = "fetch failed"
        repo.update(parse_status(git(path, opts, "status", "--porcelain=v2", "--branch", "--ignore-submodules=all")))
        log = git(path, opts, "log", "-1", "--format=%ct%x09%s").strip().split("\t", 1)
        repo["lastCommit"] = int(log[0]) if log[0].isdigit() else 0
        repo["subject"] = clip(log[1] if len(log) > 1 else "")
        repo["stashes"] = len(git(path, opts, "stash", "list").splitlines())
        heads = git(path, opts, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", "refs/heads").split()
        repo["branches"] = [clip(b, 80) for b in heads if b != repo["branch"]][:30]
        repo["merging"] = bool(git(path, opts, "rev-parse", "-q", "--verify", "MERGE_HEAD").strip())
        remote = git(path, opts, "remote", "get-url", "origin").strip()
        if not remote:
            remotes = git(path, opts, "remote").split()
            remote = git(path, opts, "remote", "get-url", remotes[0]).strip() if remotes else ""
        repo["hasRemote"] = bool(remote)
        repo["url"] = web_url(remote)
        if fetchFailed:
            repo["error"] = fetchFailed
    except (subprocess.TimeoutExpired, OSError) as e:
        repo["error"] = clip(type(e).__name__)
    return repo


def main(argv):
    fetch, depth, roots, exclude = False, 4, [], set()
    it = iter(argv)
    for a in it:
        if a == "--fetch":
            fetch = True
        elif a == "--depth":
            depth = max(1, min(8, int(next(it, "4"))))
        elif a == "--exclude":
            exclude.add(os.path.abspath(os.path.expanduser(next(it, ""))))
        else:
            roots.append(os.path.abspath(os.path.expanduser(a)))
    paths = []
    for root in roots or [os.path.expanduser("~")]:
        for p in find_repos(root, depth, exclude):
            if p not in paths:
                paths.append(p)
    with ThreadPoolExecutor(max_workers=8) as pool:
        repos = list(pool.map(lambda p: inspect(p, fetch), paths[:MAX_REPOS]))
    json.dump({"repos": repos, "fetched": fetch}, sys.stdout)


if __name__ == "__main__":
    main(sys.argv[1:])
