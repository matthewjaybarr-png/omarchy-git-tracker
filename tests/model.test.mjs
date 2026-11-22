// node tests/model.test.mjs
import { readFileSync } from "node:fs"
import vm from "node:vm"
import assert from "node:assert/strict"

const src = readFileSync(new URL("../Model.js", import.meta.url), "utf8").replace(".pragma library", "")
const M = {}
vm.runInNewContext(src + "\nObject.assign(M,{hostIcon,changes,needsPush,needsAttention,visible,badges,age,splitPaths,safeUrl,count})", { M })

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
assert.equal(M.hostIcon("https://github.com/me/r"), "\uf09b")
assert.equal(M.hostIcon("https://git.example.org/me/r"), "\udb81\udd9f")
assert.equal(M.needsAttention({ ...base, merging: true }), true)
console.log("model tests ok")
