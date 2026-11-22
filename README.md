# Git Tracker

Every git repo on your computer in one bar panel. It finds them for you and shows which
ones have changes to commit, commits to push, or new commits to pull. You can commit,
push, pull and merge without leaving the panel.

It works with your **local** git, so any host works: GitHub, GitLab, Codeberg, Gitea,
Forgejo, Bitbucket, a self-hosted server, or no remote at all. Push and pull use the
remotes and credentials you already have set up. There's no account or token to set up.

## Install

```bash
omarchy plugin add https://github.com/matthewjaybarr-png/omarchy-git-tracker.git
omarchy plugin enable matthewjaybarr.git-tracker
omarchy bar put matthewjaybarr.git-tracker --section left
```

Plugins land disabled so you can read the code first. Requires `git` and `python3` (both
ship with Omarchy). `lazygit` is optional.

## Using it

The bar icon shows how many repos need attention. Click it to open the panel.
Right-click rescans and middle-click checks the remotes.

- **The list** puts repos that need attention first, then the most recently committed.
  Each row shows the branch, badges (`3 modified`, `↑ 2 to push`, `↓ 1 to pull`,
  `merge in progress`…), the folder, and the last commit.
- **Filters**: All, Needs attention, To commit, To push, To pull, Local only. Use ←/→ to switch.
- **Search** with `/` by name, folder or branch.
- **Select a repo** to get the action card:
  - **Commit**: type a message and press Enter. All changes are staged, including new files.
  - **Push**: pushes your commits. A branch that has never been pushed is published to
    `origin` (or the first remote) with its upstream set.
  - **Pull**: pulls new commits from the upstream.
  - **Merge…**: pick another local branch, then confirm. On a conflict, fix the files,
    commit from the card, or press **Abort merge**.
- **Open** a repo on its host (double-click or Enter), in a terminal (`t`), in lazygit
  (`g`), or in your file manager (`o`).

When an action fails, the card shows git's message and a plain-English hint, such as
"pull first, then push" or "your SSH key isn't set up for this host".

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| ↑ ↓ | select repo | ← → | filter |
| Enter | open on the web | / | search |
| c | commit message | p | push |
| u | pull | m | merge |
| t | terminal | g | lazygit |
| r | rescan | f | check remotes |

## Settings

Open the widget's settings in the bar editor.

| Setting | Default | |
|---------|---------|---|
| Folders to scan | `~` | Comma separated. |
| Folders to skip | (none) | Comma separated, e.g. `~/vendor, ~/scratch`. |
| Depth | 4 | How many folders deep to look. Hidden folders, `node_modules`, `venv`, `target`, `build` and `dist` are always skipped. |
| Rescan every | 300 s | Local only, no network. |
| Check remotes in the background | off | Runs `git fetch` on every repo. Off by default because it uses the network. |
| Background check every | 1800 s | |

## Privacy and safety

- Nothing leaves your machine except the `git fetch`, `push` and `pull` you trigger (or
  turn on). Those go to the remotes you configured.
- Git never prompts for anything: `GIT_TERMINAL_PROMPT=0`, SSH in batch mode. A remote that
  needs a password fails with a hint instead of hanging.
- Branch names are validated before a merge, and commands run as argument lists, never
  through a shell. Only `https://` links are opened in the browser.
- No force push, no reset, no rebase. The most destructive button is Abort merge.

## Limits

- A repo nested inside another repo isn't listed.
- The scan stops at 400 repos.
- Commit always stages everything. To stage part of a change, use lazygit (`g`).

## Development

```bash
python3 -m unittest discover -s tests
node tests/model.test.mjs
omarchy plugin validate .
```

MIT licensed.
