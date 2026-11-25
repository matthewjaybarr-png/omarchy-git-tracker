// node tests/model.test.mjs
import { readFileSync } from "node:fs"
import vm from "node:vm"
import assert from "node:assert/strict"

const src = readFileSync(new URL("../Model.js", import.meta.url), "utf8").replace(".pragma library", "")
const M = {}
vm.runInNewContext(src + "\nObject.assign(M,{hostIcon,changes,needsPush,needsAttention,visible,badges,age,splitPaths,safeUrl,count,links,pickRemote,remoteFromTemplate})", { M })

const base = { name: "a", displayPath: "~/a", branch: "main", upstream: "origin/main", hasRemote: true, ahead: 0, behind: 0, staged: 0, modified: 0, untracked: 0, conflicts: 0, stashes: 0, error: "", lastCommit: 100 }
const clean = { ...base }
const dirty = { ...base, name: "b", modified: 2, lastCommit: 50 }
const unpushedBranch = { ...base, name: "c", upstream: "", lastCommit: 10 }
const local = { ...base, name: "d", hasRemote: false, upstream: "" }

assert.equal(M.needsAttention(clean), false)
assert.equal(M.needsAttention(dirty), true)
assert.equal(M.needsPush(unpushedBranch), true)
assert.equal(M.needsPush(local), false)
assert.deepEqual([...M.visible([clean, dirty, unpushedBranch, local], "all", "").map(r => r.name)], ["b", "c", "a", "d"])
assert.deepEqual([...M.visible([clean, dirty], "attention", "").map(r => r.name)], ["b"])
assert.deepEqual([...M.visible([clean, dirty], "all", "B").map(r => r.name)], ["b"])
assert.equal(M.count([clean, dirty, local], "noRemote"), 1)
assert.deepEqual([...M.badges(clean).map(b => b.key)], ["clean"])
assert.deepEqual([...M.badges(unpushedBranch).map(b => b.key)], ["notPushed"])
assert.equal(M.age(1000 - 7200, 1000 * 1000), "2h")
assert.deepEqual([...M.splitPaths("~/Projects, ~/My Stuff\n~/Work,")], ["~/Projects", "~/My Stuff", "~/Work"])
assert.equal(M.safeUrl("https://github.com/me/repo"), "https://github.com/me/repo")
assert.equal(M.safeUrl("file:///etc/passwd"), "")
assert.equal(M.safeUrl("https://github.com/me/$(id)"), "")
assert.equal(M.hostIcon("github"), "\uf09b")
assert.equal(M.hostIcon(""), "\udb81\udd9f")
assert.equal(M.safeUrl("https://gitlab.com/a/b/-/merge_requests/new?merge_request%5Bsource_branch%5D=f/x"), "https://gitlab.com/a/b/-/merge_requests/new?merge_request%5Bsource_branch%5D=f/x")
assert.equal(M.safeUrl("https://github.com/a/b?x=<script>"), "")

const sha = "c862545d32136673b067517b72db3b7cdee575f0"
const gh = { name: "origin", url: "https://github.com/me/r", forge: "github", pushed: true, synced: true, defaultBranch: "main" }
const keys = (r, rem) => [...M.links(r, rem)].map(l => l.key + " " + l.url)
assert.deepEqual(keys({ branch: "feat/x", head: sha }, gh), [
  "repo https://github.com/me/r", "branch https://github.com/me/r/tree/feat/x",
  "pr https://github.com/me/r/compare/feat/x?expand=1", "commit https://github.com/me/r/commit/" + sha])
assert.deepEqual(keys({ branch: "main", head: sha }, { ...gh, synced: false }), ["repo https://github.com/me/r", "branch https://github.com/me/r/tree/main"])
assert.deepEqual(keys({ branch: "main", head: sha }, { ...gh, pushed: false }), ["repo https://github.com/me/r"])
assert.deepEqual(keys({ branch: "dev", head: sha }, { ...gh, forge: "gitea", defaultBranch: "", synced: false }), ["repo https://github.com/me/r", "branch https://github.com/me/r/src/branch/dev"])
assert.deepEqual(keys({ branch: "dev", head: sha }, { ...gh, forge: "gitea", synced: false }), ["repo https://github.com/me/r", "branch https://github.com/me/r/src/branch/dev", "pr https://github.com/me/r/compare/main...dev"])
assert.deepEqual(keys({ branch: "a b", head: sha }, gh), ["repo https://github.com/me/r"])
assert.deepEqual(keys({ branch: "dev" }, { ...gh, forge: "" }), ["repo https://github.com/me/r"])
assert.deepEqual(keys({ branch: "dev" }, { ...gh, url: "" }), [])
const two = { remotes: [gh, { ...gh, name: "codeberg" }] }
assert.equal(M.pickRemote(two, "codeberg").name, "codeberg")
assert.equal(M.pickRemote(two, "").name, "origin")
assert.equal(M.pickRemote({}, ""), null)
assert.equal(M.remoteFromTemplate("git@codeberg.org:me/{name}.git", "proj"), "git@codeberg.org:me/proj.git")
assert.equal(M.needsAttention({ ...base, merging: true }), true)
console.log("model tests ok")
