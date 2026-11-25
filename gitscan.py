#!/usr/bin/env python3
"""Find local git repos and print their state as JSON for the Git Tracker panel.

Usage: gitscan.py [--fetch] [--depth N] [--remote NAME] [--host FROM=TO]... [--exclude PATH]... ROOT...
"""
import functools
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


FORGES = {"github": "github", "gitlab": "gitlab", "gitea": "gitea", "forgejo": "gitea", "bitbucket": "bitbucket"}


def parse_hosts(entries):
    """Host overrides from the settings: "from=webhost", "from=type" or "from=webhost type".

    Returns {from: (webhost, type)}; type is one of FORGES' values or "".
    """
    out = {}
    for entry in entries:
        key, _, value = entry.partition("=")
        web, kind = "", ""
        for tok in value.split():
            if tok.lower() in FORGES:
                kind = FORGES[tok.lower()]
            elif HOST_RE.match(tok) and tok[0].isalnum():
                web = tok
        if key.strip():
            out[key.strip().lower()] = (web, kind)
    return out


def guess_forge(host):
    host = host.split(":")[0].lower()
    if host == "github.com" or host.startswith("github."):
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if host == "bitbucket.org":
        return "bitbucket"
    if host == "codeberg.org" or "gitea" in host or "forgejo" in host:
        return "gitea"
    return ""


@functools.lru_cache(maxsize=None)
def ssh_hostname(alias):
    """The real host behind an ~/.ssh/config alias (`Host work` + `HostName github.com`); alias if none."""
    try:
        r = subprocess.run(["ssh", "-G", "--", alias], capture_output=True, text=True, timeout=5, env=ENV)
    except (subprocess.TimeoutExpired, OSError):
        return alias
    for line in r.stdout.splitlines():
        if line.startswith("hostname "):
            name = line[9:].strip()
            return name if HOST_RE.match(name) and name[0].isalnum() else alias
    return alias


def web_url(remote, hosts=None, resolve=None):
    """Turn a git remote into (browsable https URL, forge type); ("", "") if it isn't one.

    hosts: parse_hosts() overrides. resolve: maps an ssh host alias to the real host.
    """
    remote = (remote or "").strip()
    m = re.match(r"^(?:ssh://)?[\w.-]+@([^:/]+)[:/](.+)$", remote) or re.match(
        r"^https?://(?:[^@/]+@)?([^/]+)/(.+)$", remote)
    if not m:
        return "", ""
    host, path = m.group(1), m.group(2)
    if path.endswith(".git"):
        path = path[:-4]
    if remote.startswith("ssh://"):
        path = re.sub(r"^\d+/", "", path)  # ssh://git@host:22/owner/repo — the port is not part of the web path
    path = path.strip("/")
    if not HOST_RE.match(host) or not host[0].isalnum() or not path or not PATH_RE.match(path) or ".." in path:
        return "", ""
    hosts = hosts or {}
    web, kind = hosts.get(host.lower(), ("", ""))
    if not web and resolve and not remote.startswith(("http://", "https://")):
        host = resolve(host)
        web2, kind2 = hosts.get(host.lower(), ("", ""))
        web, kind = web2, kind or kind2
    host = web or host
    return "https://%s/%s" % (host, path), kind or guess_forge(host)


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
SAFE_CONFIG = [("core.fsmonitor", "false"), ("core.hooksPath", "/dev/null"), ("log.showSignature", "false")]
# Local keys that make `git fetch` run a program (env GIT_SSH_COMMAND already overrides core.sshCommand).
FETCH_RISK_RE = re.compile(r"^(core\.gitproxy|core\.askpass|credential\..*|remote\..*\.(uploadpack|receivepack)"
                           r"|protocol\..*|url\..*)$", re.S)
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_ASKPASS": "",
       "SSH_ASKPASS": "", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def local_keys(path):
    """Keys set by the repo's own config (local and worktree scope, includes too); None if unreadable.

    Git prints section and variable names lowercased but keeps the subsection (e.g. a filter
    driver's name) exactly as written, so keys are used as-is: lowercasing would miss drivers.
    """
    r = subprocess.run(["git", "-C", path, "config", "--list", "--show-scope", "-z"],
                       capture_output=True, text=True, timeout=15, env=ENV)
    if r.returncode != 0:
        return None
    parts = r.stdout.split("\0")  # scope NUL key LF value NUL ...
    return [entry.split("\n", 1)[0] for scope, entry in zip(parts[::2], parts[1::2])
            if scope in ("local", "worktree")]


def safe_env(keys):
    """ENV plus overrides that switch off fsmonitor, hooks, signature checks and every filter
    driver the repo defines for itself. Passed as GIT_CONFIG_KEY_n/VALUE_n, not `-c`, so a
    driver name containing `=` or other odd characters is still matched exactly."""
    config = list(SAFE_CONFIG)
    names = {k[len("filter."):k.rindex(".")] for k in keys if k.startswith("filter.") and k.count(".") >= 2}
    for name in sorted(names):
        config += [("filter.%s.%s" % (name, part), "") for part in ("clean", "smudge", "process")]
        config.append(("filter.%s.required" % name, "false"))
    env = {k: v for k, v in ENV.items() if not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env["GIT_CONFIG_COUNT"] = str(len(config))
    for i, (key, value) in enumerate(config):
        env["GIT_CONFIG_KEY_%d" % i], env["GIT_CONFIG_VALUE_%d" % i] = key, value
    return env


def git(path, env, *args, timeout=15):
    r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout, env=env)
    return r.stdout if r.returncode == 0 else ""


def remotes(path, env, repo, prefer, hosts):
    """Each remote with its web link, preferred remote first, and whether the current branch is on it."""
    names = sorted(git(path, env, "remote").split(), key=lambda n: (n != prefer, n != "origin"))[:10]
    refs = {}
    for line in git(path, env, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(symref)", "refs/remotes").splitlines():
        ref, sha, sym = (line.split("\t") + ["", ""])[:3]
        refs[ref] = (sha, sym)
    out = []
    for n in names:
        url, forge = web_url(git(path, env, "remote", "get-url", n).strip(), hosts, ssh_hostname)
        tip = refs.get("refs/remotes/%s/%s" % (n, repo["branch"]))
        default = refs.get("refs/remotes/%s/HEAD" % n, ("", ""))[1]
        prefix = "refs/remotes/%s/" % n
        out.append({"name": clip(n, 40), "url": url, "forge": forge, "pushed": bool(tip),
                    "synced": bool(tip) and tip[0] == repo["head"],
                    "defaultBranch": clip(default[len(prefix):], 80) if default.startswith(prefix) else ""})
    return out


def inspect(path, fetch, prefer="origin", hosts=None):
    home = os.path.expanduser("~")
    repo = {"name": clip(os.path.basename(path), 80), "path": path,
            "displayPath": clip("~" + path[len(home):] if path.startswith(home) else path),
            "error": ""}
    try:
        fetchFailed = False
        keys = local_keys(path)
        if keys is None:  # fail closed: never run status in a repo whose config we couldn't read
            repo["error"] = "unreadable config"
            return repo
        env = safe_env(keys)
        if fetch:
            if any(FETCH_RISK_RE.match(k) for k in keys):
                fetchFailed = "fetch skipped: repo config"
            elif subprocess.run(["git", "-C", path, "fetch", "--quiet", "--prune", "--no-recurse-submodules"],
                                capture_output=True, timeout=30, env=env).returncode != 0:
                fetchFailed = "fetch failed"
        repo.update(parse_status(git(path, env, "status", "--porcelain=v2", "--branch", "--ignore-submodules=all")))
        log = git(path, env, "log", "-1", "--format=%ct%x09%s").strip().split("\t", 1)
        repo["lastCommit"] = int(log[0]) if log[0].isdigit() else 0
        repo["subject"] = clip(log[1] if len(log) > 1 else "")
        repo["stashes"] = len(git(path, env, "stash", "list").splitlines())
        heads = git(path, env, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", "refs/heads").split()
        repo["branches"] = [clip(b, 80) for b in heads if b != repo["branch"]][:30]
        repo["merging"] = bool(git(path, env, "rev-parse", "-q", "--verify", "MERGE_HEAD").strip())
        head = git(path, env, "rev-parse", "-q", "--verify", "HEAD").strip()
        repo["head"] = head if re.match(r"^[0-9a-f]{7,64}$", head) else ""
        repo["remotes"] = remotes(path, env, repo, prefer, hosts)
        repo["hasRemote"] = bool(repo["remotes"])
        first = repo["remotes"][0] if repo["remotes"] else {}
        repo["url"], repo["forge"] = first.get("url", ""), first.get("forge", "")
        if fetchFailed:
            repo["error"] = fetchFailed
    except (subprocess.TimeoutExpired, OSError) as e:
        repo["error"] = clip(type(e).__name__)
    return repo


def main(argv):
    fetch, depth, roots, exclude, prefer, hosts = False, 4, [], set(), "origin", []
    it = iter(argv)
    for a in it:
        if a == "--fetch":
            fetch = True
        elif a == "--remote":
            prefer = next(it, "origin")
        elif a == "--host":
            hosts.append(next(it, ""))
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
        repos = list(pool.map(lambda p: inspect(p, fetch, prefer, parse_hosts(hosts)), paths[:MAX_REPOS]))
    json.dump({"repos": repos, "fetched": fetch}, sys.stdout)


if __name__ == "__main__":
    main(sys.argv[1:])
