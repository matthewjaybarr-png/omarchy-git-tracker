# Changelog

## 1.2.0

- Links work with SSH host aliases: `git@github-work:me/repo` now opens `github.com`, using
  what `ssh -G` says the alias points at.
- New "Web host overrides" setting for servers whose web address differs from their git
  address, or whose site type can't be guessed (e.g. `git.corp=gitlab.corp.com gitlab`).
- The action card links to the current branch, a new pull request for it, and the last commit,
  on GitHub, GitLab, Gitea/Forgejo/Codeberg and Bitbucket.
- A repo with several remotes shows a button per remote; pick one and the links follow it. The
  "Remote whose site links open" setting picks the default (`origin`).
- Local-only repos get an "Add remote" field, prefilled from the new "Remote for local-only
  repos" template setting. Add it, then press Push to publish.
- Codeberg, Gitea and Forgejo remotes get a git icon instead of the generic globe.

## 1.1.0

- Hide a repo from the panel with the eye button or `h`. It's added to the "Folders to skip"
  setting, so removing it there brings the repo back.

## 1.0.2

- Filter drivers with mixed-case names (or `=` in the name) are now switched off during scans too.
  Overrides are passed through `GIT_CONFIG_KEY_n` environment variables instead of `-c`.
- A repo whose config can't be read is skipped rather than scanned.

## 1.0.1

- Scans and fetches no longer run programs set in a repo's own config (fsmonitor, filters,
  signature checks, hooks, credential helpers and similar). Submodules are not entered.
- Merge refuses to run if a different branch is now checked out than the one you confirmed.

## 1.0.0

- First release: finds local repos and shows commit / push / pull status with filters and search.
- Commit, push (publishes new branches), pull, merge and abort merge from the panel.
- Opens repos on any https git host, in a terminal, in lazygit or in the file manager.
- Optional background `git fetch`.
