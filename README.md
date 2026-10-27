# Atlas

A local wiki for what runs where, and why. **A new installation starts empty.**

This repository contains the application, not an inventory. It does not import home projects, assume a life-admin dashboard, scan your machine, or copy records from another computer. Add your first page in the wiki, use `atlas new`, or explicitly run a folder scan.

## Install on macOS

```sh
brew install git gh uv
gh auth login
gh auth setup-git
mkdir -p ~/Developer
git clone --depth 1 https://github.com/cwkoenigs/atlas.git ~/Developer/atlas
uv tool install --editable ~/Developer/atlas
uv tool update-shell
export PATH="$HOME/.local/bin:$PATH"
atlas wiki
```

Sign into an account with access to the private repositories. `uv` installs the terminal library, `ds-cli-design`, from GitHub automatically; it does not push anything to GitHub. No Hermes, dashboard-style checkout, Documents folder, or home-machine configuration is required.

The wiki runs at **http://localhost:8788/**, bound to the local machine only. macOS and Linux have the locking primitives the app uses; native Windows is not supported.

## Everyday use

```sh
atlas wiki                    # open the wiki; an initial install has zero pages
atlas new                     # draft your first page
atlas map --no-check          # terminal map without running check commands
atlas                         # terminal map and picker; may run existing card checks
atlas 2                       # read the page numbered 2 on the map
atlas open 2                  # open its markdown file
atlas check                   # explicitly run the saved checks
atlas help
```

Use a map number or a word from a page's name, not an internal ID. `atlas` refreshes checks when the last run is over six hours old. Check commands are user-authored trusted shell code, not sandboxed expressions. Stale or legacy results are not treated as current passes.

The wiki supports whole-page/section editing and preview, links and backlinks, search, history/diff/restore, and draft/active/retired lifecycle actions. It defaults to light mode and remembers an explicit theme change. Edits detect conflicts rather than overwriting a newer version.

## Your inventory stays local

| Path | Purpose | Included in this app repository? |
|---|---|---|
| `inbox/` | Draft pages | No |
| `cards/` | Active pages | No |
| `retired/` | Retired pages | No |
| `.state/` | Local history, results, server metadata and recovery journals | No |
| `ATLAS.md` | Generated summary | No |
| `atlas.local.json` | This machine's places and optional integrations | No |
| `atlas.json` | Neutral application defaults | Yes |
| `templates/card.md` | Blank page template | Yes |

All inventory folders are ignored—not just `personal/`. A personal flag still classifies a page inside the inventory; removing that flag does **not** upload the page. Git pulls/pushes in this application repository update code, not your records. Back up your inventory and `.state/` separately. A separately managed `ATLAS_DIR` can use its own backup/versioning policy.

Earlier versions of this private repository bundled inventory records. They were removed from the current tree, not erased from historical commits. The shallow-clone command above does not fetch that old history. Updating an older checkout removes unchanged formerly tracked records; preserve your own inventory before updating if you want to keep those records. Git refuses an update that would overwrite uncommitted edits—do not force it or run `git clean` on your inventory.

## Local configuration (optional)

You do not need to edit configuration to start. The default place is `this-mac` (This computer), and external HTML export is disabled.

To add your own places or change settings, create ignored `atlas.local.json` beside `atlas.json`:

```json
{
  "hosts": {
    "this-mac": "This computer",
    "work-server": "Work server"
  },
  "wiki_port": 8788
}
```

Local keys replace the matching defaults; `hosts` replaces the entire host map. Restart after changing config: `atlas wiki --stop`, then `atlas wiki`.

`html_out` and `template` are optional legacy dashboard-export settings. Both default to `null`. They are unrelated to running the standalone wiki; leave them disabled unless you deliberately configure an integration on this machine. The wiki's HTML/CSS is already included in the package.

## Scan only when you ask

```sh
atlas scan ~/Developer --dry-run   # inspect the proposed drafts; write nothing
atlas scan ~/Developer             # explicitly create local draft pages
```

Scanning reads folder facts and creates drafts only for unmapped directories. It does not move or modify the projects themselves. It leaves the reason (`why`) for you to fill in. There is no automatic scan or inventory import during installation or startup.

## Update

```sh
git -C ~/Developer/atlas pull --ff-only
atlas wiki
```

The installation is editable, so pulling updates the command. The wiki restarts when its code changes. To stop it: `atlas wiki --stop`.

## Mutation safety and regression checks

CLI and wiki writers share a reentrant per-inventory `flock` plus a thread lock. Card and check-state files are replaced atomically after flushing and fsync. Saves validate the exact captured card text; a stale CLI save fails with a reload message and a stale wiki form retains the submitted text for review. Lifecycle moves refuse destination collisions and repeated retirement is harmless. Checks run outside the card lock and commit only their own results into freshly loaded state. Timed-out or cancelled checks receive process-group TERM, then a bounded KILL fallback; communication failures also clean up and reap the check before propagating the error.

Every mutation preserves its on-disk preimage in local history, including an external editor's changes. History IDs must match `a-` plus six lowercase hexadecimal digits. Valid unterminated JSONL entries receive their missing delimiter; an incomplete final fragment is kept in a `.jsonl.tail-*` file before the healthy history is atomically replaced. Invalid complete entries and interior corruption fail with an error instead of being silently discarded. History and metadata remain under the existing personal-data gitignore rules.

Lifecycle moves write a durable version-2 `.state/move.json` intent before publishing the destination as a hard link to a complete staging file. Source removal uses an atomic exclusive rename into a journaled, private `.atlas-claim-<token>/source` directory beside the source. Only then are the captured inode and exact contents validated. A changed source is preserved and restored with an exclusive hard link when its original name is free; a newer original-name file is never overwritten. Rollback likewise captures the destination into a journaled `.atlas-claim-<token>/destination` backup and validates the captured file; unknown destinations are retained and exclusively restored when possible. Ordinary claim failures roll back the owned destination. Reads, mutations, and wiki startup recover interrupted forward moves under the inventory lock, completing history idempotently; readers cannot see the intermediate claim state. Changed files, malformed/older journals, and interrupted rollback fail closed with an explicit reconciliation error.

Claimed source and rollback inodes **remain on disk**, with original permissions, even after success or validation: an external editor holding an open file descriptor may still write to them. Hidden staging files are retained too; none are loaded as cards. These backups consume space and require deliberate manual reconciliation/cleanup after editors have closed; Atlas does not automatically delete them. On a conflict, preserve `.state/move.json`, `.atlas-claim-*` directories, and `.atlas-move-*` files while comparing source, destination, and captured versions. A rollback-phase journal blocks automatic forward replay. Atomic exclusive rename requires macOS `renamex_np(RENAME_EXCL)` or Linux `renameat2(RENAME_NOREPLACE)`; unavailable operations/filesystems fail closed. Destination publication and exclusive restoration require hard-link support. This protects captured files against outside writers without claiming multi-file ACID for nonparticipating editors.

The lock coordinates Atlas processes on one machine. Editors that do not take that lock can still race during an in-place write; reload after an external edit. Graceful shutdown drains accepted writes and closes the listener before persisting an instance-bound completion marker in `.state/wiki-server.json`, so an unreaped exited process does not block port migration. A stop that is still draining after eight seconds reports an error. Forced termination cannot drain writes. Wiki responses use `Referrer-Policy: same-origin` so browser forms retain their origin; strict Origin and CSRF validation remain in force. Historical CRLF revisions render through the core parser and restore with their exact original bytes.

Run the isolated stdlib suite with the Python interpreter in the installed Atlas tool environment, `PYTHONPATH=src`, and an explicit disposable `TMPDIR`. The suite also needs Node.js for the shipped JavaScript search tests. Existing card checks are never used by the suite. See [the original review map](docs/review-resolution.md), [second-review map](docs/review2-resolution.md), and [observed red/green results](docs/regression-log.md).
