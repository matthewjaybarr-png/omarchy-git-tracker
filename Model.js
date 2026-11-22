.pragma library

// Pure helpers for the Git Tracker panel; no QML, so tests can load them in node.

var FILTERS = ["all", "attention", "commit", "push", "pull", "noRemote"]

function changes(r) {
  return (r.staged || 0) + (r.modified || 0) + (r.untracked || 0) + (r.conflicts || 0)
}

// A branch with a remote but no upstream has never been pushed.
function needsPush(r) {
  return (r.ahead || 0) > 0 || (r.hasRemote && !r.upstream && r.branch !== "(detached)")
}

function needsPull(r) { return (r.behind || 0) > 0 }
function needsCommit(r) { return changes(r) > 0 }

function needsAttention(r) {
  return needsCommit(r) || needsPush(r) || needsPull(r) || !!r.error || !!r.merging
}

function matches(r, filter) {
  switch (filter) {
    case "attention": return needsAttention(r)
    case "commit": return needsCommit(r)
    case "push": return needsPush(r)
    case "pull": return needsPull(r)
    case "noRemote": return !r.hasRemote
    default: return true
  }
}

function count(repos, filter) {
  var n = 0
  for (var i = 0; i < repos.length; i++) if (matches(repos[i], filter)) n++
  return n
}

// Attention first, then most recently committed.
function visible(repos, filter, query) {
  var q = String(query || "").toLowerCase()
  return repos.filter(function(r) {
    if (!matches(r, filter)) return false
    if (!q) return true
    return (r.name + " " + r.displayPath + " " + r.branch).toLowerCase().indexOf(q) !== -1
  }).sort(function(a, b) {
    var d = (needsAttention(b) ? 1 : 0) - (needsAttention(a) ? 1 : 0)
    return d !== 0 ? d : (b.lastCommit || 0) - (a.lastCommit || 0)
  })
}

// Badges as {key, n, urgent}; the panel turns keys into translated text.
function badges(r) {
  var out = []
  if (r.merging) out.push({ key: "merging", n: 0, urgent: true })
  if (r.conflicts) out.push({ key: "conflicts", n: r.conflicts, urgent: true })
  if (r.staged) out.push({ key: "staged", n: r.staged, urgent: false })
  if (r.modified) out.push({ key: "modified", n: r.modified, urgent: false })
  if (r.untracked) out.push({ key: "untracked", n: r.untracked, urgent: false })
  if (r.ahead) out.push({ key: "ahead", n: r.ahead, urgent: true })
  else if (needsPush(r)) out.push({ key: "notPushed", n: 0, urgent: true })
  if (r.behind) out.push({ key: "behind", n: r.behind, urgent: true })
  if (r.stashes) out.push({ key: "stashes", n: r.stashes, urgent: false })
  if (!r.hasRemote) out.push({ key: "noRemote", n: 0, urgent: false })
  if (r.error) out.push({ key: "error", n: 0, urgent: true })
  if (out.length === 0) out.push({ key: "clean", n: 0, urgent: false })
  return out
}

function age(epochSec, nowMs) {
  if (!epochSec) return ""
  var s = Math.max(0, Math.floor(nowMs / 1000) - epochSec)
  if (s < 3600) return Math.max(1, Math.floor(s / 60)) + "m"
  if (s < 86400) return Math.floor(s / 3600) + "h"
  if (s < 86400 * 30) return Math.floor(s / 86400) + "d"
  if (s < 86400 * 365) return Math.floor(s / (86400 * 30)) + "mo"
  return Math.floor(s / (86400 * 365)) + "y"
}

// Comma/newline separated list from a setting; paths may contain spaces.
function splitPaths(value) {
  return String(value || "").split(/[,\n]/).map(function(s) { return s.trim() }).filter(function(s) { return s !== "" })
}

// Nerd Font glyph for the remote's host; any other host gets a generic globe.
function hostIcon(url) {
  var u = String(url || "")
  if (/^https:\/\/github\.com\//.test(u)) return "\uf09b"
  if (/^https:\/\/gitlab\./.test(u)) return "\uf296"
  if (/^https:\/\/bitbucket\.org\//.test(u)) return "\uf171"
  return "\udb81\udd9f"
}

// Only https links reach the browser.
function safeUrl(url) {
  return /^https:\/\/[A-Za-z0-9.-]+(:\d+)?\/[A-Za-z0-9._~\/-]+$/.test(String(url || "")) ? url : ""
}
