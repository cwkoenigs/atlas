# atlas

What runs where, and why. One markdown card per thing (a site, a job, a repo, a folder, a device), each with a check command that proves it is still true, and a wiki built from all of them to read at the start of the day.

Atlas never moves anything. It records where a thing already is, so an hour spent untangling it is not spent twice.

## Using it

```sh
atlas              # the map, then a picker: type to filter, arrows to move, Enter opens, Esc quits
atlas 2            # read card 2
atlas pi           # read the card with "pi" in its name (a picker if several match)
atlas open 2       # open card 2's file, with the full untangle story
atlas new          # a form to draft a card
atlas wiki         # the whole atlas as a wiki in your browser
atlas help         # everything else
```

You never type an id. Every command that takes a card (`open`, `check`, `confirm`, `promote`, `retire`, `personal`) takes a number from the map or a word from the card's name. `atlas` re-runs the checks when the last run is over 6 hours old; `atlas check` forces it. `atlas map --no-check` and `atlas today --no-check` use cached results without running commands; `--no-check` wins if `--check` is also supplied. `--plain` prints without colour or widgets (also automatic when piped).

The look comes from [ds-cli-design](https://github.com/cwkoenigs/ds-cli-design), the terminal design system (roles, glyphs, the 80-column grid, frames for anything that needs you, the dog-and-cat banner). Atlas imports it; it holds no colours or glyphs of its own.

## The wiki: `atlas wiki`

`atlas wiki` opens the atlas as a wiki at http://localhost:8788 (it starts the wiki if it is not running; bare `atlas` keeps it running too, and the life-admin hub's Atlas tile goes there). Light by default; the Dark button switches and remembers. `atlas wiki 5` opens one card's page; `atlas wiki --stop` stops it after active writes finish. Idle HTTP connections do not delay shutdown. If `wiki_port` changes, `atlas wiki` discovers the previous listener through `.state/wiki-server.json`, drains it, and starts on the configured port. Host and Origin validation always use the socket's bound port.

- **A page per card**, with an at-a-glance box (status, place, kind, where, what, why, where to edit it, how to reach it, the check) and buttons that do what the commands do: run the check, still true, promote, make personal or share, retire, bring back.
- **Links.** `[[Page name]]` (or `[[Page name|shown text]]`) in any card links to that page; a missing page shows as a dashed link that creates it. A path in backticks, like `` `~/Developer/atlas` ``, links to the page about that folder. Each page lists what it links to, what links to it, what it is part of, what is inside it, and what shares its repo.
- **Editing.** Edit a whole page or one section (the `edit` link by each heading), preview before saving, and leave a summary. If the file changed while you were editing (the CLI, an agent, another window), it tells you instead of overwriting. It refuses anything that looks like a password, token or key. Renaming a page keeps the old name working and refuses a name owned by another page, including its aliases. Related-page forms retain stable IDs; you can also enter names, quoting any name that contains a comma.
- **History.** Every version of every page, from the wiki, the CLI, a scan, an editor or git, newest first; compare any two, see what changed, restore an old version. Kept in `.state/history/`, never in git, so personal pages' history stays on this Mac too.
- **Finding things.** Search as you type in the top bar (`/` jumps there); full-text search with highlighted matches; Recent changes; Needs a look (with "Check everything now"); All pages A to Z; a page for each place and each kind; Wanted pages (links nobody has written); Retired pages; Random page.

It is served by atlas itself (Python's standard library) on 127.0.0.1 only. It answers only to `localhost` and accepts a form only from its own pages, so another website cannot drive it. Its look is the Data Science design system's docs-portal style: `src/atlas_cli/wiki/shell.html` carries the generated theme regions, so `python3 ~/Developer/dashboard-style/scripts/build_theme.py --into src/atlas_cli/wiki/shell.html` refreshes it after a design change and `check_theme.py` checks it.

## Install

```sh
# with both repos checked out (changes to either show up at once):
uv tool install --editable ~/Developer/atlas --with-editable ~/Developer/ds-cli-design --no-sources
# with only atlas checked out (ds-cli-design comes from GitHub):
uv tool install --editable ~/Developer/atlas
cp ~/Developer/atlas/bin/atlas-shim /opt/homebrew/bin/atlas   # if ~/.local/bin is not on your PATH
```

Editable means a `git pull` updates the command. The cards stay in `~/Developer/atlas` (set `ATLAS_DIR` to use another folder).

## Finding what's there: `atlas scan`

```sh
atlas scan --dry-run      # what it would draft, nothing written
atlas scan                # ~/Developer by default; or atlas scan ~/some/folder
```

For each folder directly inside, it reads the git remote and state, what the README or package says it is, how it deploys (`.vercel`, `vercel.json`, Fly, GitHub Actions), what on this Mac uses it (launchd jobs, Hermes cron, agent skills, uv tools) and other clones of the same repo. A folder no card mentions gets a draft in the inbox with `where`, `what`, a check, those facts, and gotchas (no remote, uncommitted or unpushed work, not in git). `why` stays empty: only you know it. Drafts are personal (this Mac only) until you share them with `atlas personal <n> --undo`; `--shared` drafts them shared. The scan only reads; it never changes the folders.

## After untangling something

Ask Hermes to "put this in the atlas"; the `atlas` skill turns the session into a card. By hand:

```sh
atlas new "Ringneck billing site" --kind site --host vercel     # drafts inbox/ringneck-billing-site.md
# fill in the card, then:
atlas promote a-7e21c4      # inbox -> cards, once what/why/where are filled and the check passes
```

## The lifecycle

| Stage | Folder | Means | Move it with |
|---|---|---|---|
| Draft | `inbox/` | Captured, not yet confirmed | `atlas promote ID` |
| Active | `cards/` | Confirmed true; re-checked daily | `atlas confirm ID` after re-reading it |
| Retired | `retired/` | The thing is gone; the card keeps the history | `atlas retire ID --reason "..."` |

## Personal cards

`atlas personal ID` moves a card into its folder's `personal/` subfolder, which git ignores. Home and family things (the kids' school tracker, the home Pi, the old Mac, the life-admin dashboards) live there, so they stay on Clark's own Mac and never reach GitHub or a work computer. `ATLAS.md` is built on each machine and is not committed either. `atlas new --personal` starts a card as personal; `atlas personal ID --undo` shares it.

## Commands

| Command | Does |
|---|---|
| `atlas` | The map and the picker; checks again if the last run is over 6 h old |
| `atlas new "Title" --kind K --host H` | Draft a card in `inbox/` (also `--where --what --why --source --entry --check --link --personal`) |
| `atlas check [ID ...]` | Run checks |
| `atlas promote ID` | Inbox to cards (refuses if a required field is empty or the check fails; `--force` for something known to be down) |
| `atlas confirm ID` | Stamp today as the last time it was confirmed true |
| `atlas retire ID --reason TEXT` | Cards to retired |
| `atlas personal ID [--undo]` | Keep a card on this Mac only, or share it again |
| `atlas show ID` | Read cards in the terminal |
| `atlas open ID [--edit]` | Open a card file in its app (or `$EDITOR`) |
| `atlas wiki [ID]` | Open the wiki (or one card's page); `--stop` stops it, `--no-open` only starts it. `atlas page` does the same |
| `atlas lint` | Missing fields, unknown hosts, links to nothing |

ID can be the number from the map, any word from the card's name, its file name, or its id.

## A card

```yaml
id: a-7e21c4
title: Ringneck billing site
kind: site          # site | app | service | job | repo | folder | domain | device
host: vercel        # a key in atlas.json: groups the morning page by place
where: Vercel project ringneck-billing (team code-harvest)
what: The billing site. Builds from site/ringneck-billing in the ringneck-pork repo.
why: Ringneck Pork's billing pages; production deploy on every push to main.
source: ~/Developer/ringneck-pork/site/ringneck-billing      # where you edit it
entry: https://ringneck-billing.vercel.app                  # how you reach it
check: curl -fsS -o /dev/null -m 10 https://ringneck-billing.vercel.app
links: [a-19d6ef, a-4b90d2]       # related cards, drawn in the Connections graph
confidence: confirmed             # confirmed | believed | guess
confirmed: 2026-10-22
```

Below the frontmatter: **Short version** (what to remember), **Untangled** (what looked true, what is, how we know), **To change it**, **Gotchas**. The template is `templates/card.md`. Existing plain frontmatter and comments remain readable. Saves use JSON-escaped quoted strings when needed and JSON string lists, preserving literal quotes, commas, comment markers, and embedded newlines.

## Files

| Path | What it is | In git |
|---|---|---|
| `cards/`, `inbox/`, `retired/` | The cards. The only thing you edit | yes |
| `*/personal/` | Personal cards | no |
| `ATLAS.md` | The morning page in markdown, rebuilt by `atlas` and `atlas check` | no |
| `atlas.json` | Places (hosts) and their names, the stale threshold, the wiki's port (`wiki_port`, default 8788), and the life-admin page that forwards to the wiki | yes |
| `src/atlas_cli/` | The CLI: `core.py` (cards, checks, pages), `cli.py` (the terminal), `picker.py` (cards into the design system's picker), `history.py` (every version of every card), `scan.py`, `wiki/` (the wiki) | yes |
| `pyproject.toml` | Package `atlas-map`, command `atlas`; needs ds-cli-design and markdown-it-py | yes |
| `.state/` | Last check results, page history, the wiki's log | no |

On a new machine: clone to `~/Developer/atlas`, `uv tool install --editable ~/Developer/atlas`, run `atlas`. If `atlas.json`'s `template` path does not exist there, it skips the life-admin page; `atlas wiki` works anywhere.

## Mutation safety and regression checks

CLI and wiki writers share a reentrant per-inventory `flock` plus a thread lock. Card and check-state files are replaced atomically after flushing and fsync. Saves validate the exact captured card text; a stale CLI save fails with a reload message and a stale wiki form retains the submitted text for review. Lifecycle moves refuse destination collisions and repeated retirement is harmless. Checks run outside the card lock and commit only their own results into freshly loaded state. Timed-out or cancelled checks receive process-group TERM, then a bounded KILL fallback; communication failures also clean up and reap the check before propagating the error.

Every mutation preserves its on-disk preimage in local history, including an external editor's changes. History IDs must match `a-` plus six lowercase hexadecimal digits. Valid unterminated JSONL entries receive their missing delimiter; an incomplete final fragment is kept in a `.jsonl.tail-*` file before the healthy history is atomically replaced. Invalid complete entries and interior corruption fail with an error instead of being silently discarded. History and metadata remain under the existing personal-data gitignore rules.

Lifecycle moves write a durable version-2 `.state/move.json` intent before publishing the destination as a hard link to a complete staging file. Source removal uses an atomic exclusive rename into a journaled, private `.atlas-claim-<token>/source` directory beside the source. Only then are the captured inode and exact contents validated. A changed source is preserved and restored with an exclusive hard link when its original name is free; a newer original-name file is never overwritten. Rollback likewise captures the destination into a journaled `.atlas-claim-<token>/destination` backup and validates the captured file; unknown destinations are retained and exclusively restored when possible. Ordinary claim failures roll back the owned destination. Reads, mutations, and wiki startup recover interrupted forward moves under the inventory lock, completing history idempotently; readers cannot see the intermediate claim state. Changed files, malformed/older journals, and interrupted rollback fail closed with an explicit reconciliation error.

Claimed source and rollback inodes **remain on disk**, with original permissions, even after success or validation: an external editor holding an open file descriptor may still write to them. Hidden staging files are retained too; none are loaded as cards. These backups consume space and require deliberate manual reconciliation/cleanup after editors have closed; Atlas does not automatically delete them. On a conflict, preserve `.state/move.json`, `.atlas-claim-*` directories, and `.atlas-move-*` files while comparing source, destination, and captured versions. A rollback-phase journal blocks automatic forward replay. Atomic exclusive rename requires macOS `renamex_np(RENAME_EXCL)` or Linux `renameat2(RENAME_NOREPLACE)`; unavailable operations/filesystems fail closed. Destination publication and exclusive restoration require hard-link support. This protects captured files against outside writers without claiming multi-file ACID for nonparticipating editors.

The lock coordinates Atlas processes on one machine. Editors that do not take that lock can still race during an in-place write; reload after an external edit. Graceful shutdown drains accepted writes and closes the listener before persisting an instance-bound completion marker in `.state/wiki-server.json`, so an unreaped exited process does not block port migration. A stop that is still draining after eight seconds reports an error. Forced termination cannot drain writes. Wiki responses use `Referrer-Policy: same-origin` so browser forms retain their origin; strict Origin and CSRF validation remain in force. Historical CRLF revisions render through the core parser and restore with their exact original bytes.

Run the isolated stdlib suite with the installed Atlas interpreter and local sources:

```sh
PYTHONPATH="$PWD/src" /Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python -m unittest discover -v
PYTHONPATH="$PWD/src" /Users/clarkkoenigs/.local/share/uv/tools/atlas-map/bin/python -m compileall -q src tests
```

The suite requires Node.js for the shipped JavaScript suggestion tests. Test inventories and check working directories are disposable directories under `TMPDIR`; no existing card check commands run. HTTP shutdown tests use socket pairs so they also run where TCP binding is denied. See [the 26-finding resolution map](docs/review-resolution.md) and [observed red/green results](docs/regression-log.md).
