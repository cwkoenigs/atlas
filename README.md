# atlas

What runs where, and why. One markdown card per thing (a site, a job, a repo, a folder, a device), each with a check command that proves it is still true, and one page built from all of them to read at the start of the day.

Atlas never moves anything. It records where a thing already is, so an hour spent untangling it is not spent twice.

## Using it

```sh
atlas              # the map, then a picker: type to filter, arrows to move, Enter opens, Esc quits
atlas 2            # read card 2
atlas pi           # read the card with "pi" in its name (a picker if several match)
atlas open 2       # open card 2's file, with the full untangle story
atlas new          # a form to draft a card
atlas help         # everything else
```

You never type an id. Every command that takes a card (`open`, `check`, `confirm`, `promote`, `retire`, `personal`) takes a number from the map or a word from the card's name. `atlas` re-runs the checks when the last run is over 6 hours old; `atlas check` forces it. `--plain` prints without colour or widgets (also automatic when piped).

The look is the ds-next terminal design system v1: `src/atlas_cli/ui_style.py` and `widgets.py` are copied from it (roles, glyphs, the 80-column grid, frames for anything that needs you, the dog-and-cat banner).

## Install

```sh
uv tool install --editable ~/Developer/atlas     # puts `atlas` in ~/.local/bin
cp ~/Developer/atlas/bin/atlas-shim /opt/homebrew/bin/atlas   # if ~/.local/bin is not on your PATH
```

Editable means a `git pull` here updates the command. The cards stay in `~/Developer/atlas` (set `ATLAS_DIR` to use another folder).

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
| `atlas today [--no-check]` | Check everything, rebuild the pages, list what needs a look |
| `atlas new "Title" --kind K --host H` | Draft a card in `inbox/` (also `--where --what --why --source --entry --check --link --personal`) |
| `atlas check [ID ...]` | Run checks |
| `atlas promote ID` | Inbox to cards (refuses if a required field is empty or the check fails; `--force` for something known to be down) |
| `atlas confirm ID` | Stamp today as the last time it was confirmed true |
| `atlas retire ID --reason TEXT` | Cards to retired |
| `atlas personal ID [--undo]` | Keep a card on this Mac only, or share it again |
| `atlas show ID`, `atlas find TEXT` | Read cards in the terminal |
| `atlas open ID [--edit]` | Open a card file in its app (or `$EDITOR`) |
| `atlas page` | Open the card page in the browser |
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

Below the frontmatter: **Short version** (what to remember), **Untangled** (what looked true, what is, how we know), **To change it**, **Gotchas**. The template is `templates/card.md`.

## Files

| Path | What it is | In git |
|---|---|---|
| `cards/`, `inbox/`, `retired/` | The cards. The only thing you edit | yes |
| `*/personal/` | Personal cards | no |
| `ATLAS.md` | The morning page, built by `atlas today` | no |
| `atlas.json` | Places (hosts) and their names, the stale threshold, where the HTML page goes | yes |
| `src/atlas_cli/` | The CLI: `core.py` (cards, checks, pages), `cli.py` (the terminal), `picker.py`, and the design system's `ui_style.py` and `widgets.py` | yes |
| `pyproject.toml` | Package `atlas-map`, command `atlas`; needs rich and prompt_toolkit | yes |
| `.state/` | Last check results | no |

On a new machine: clone to `~/Developer/atlas`, `uv tool install --editable ~/Developer/atlas`, run `atlas`. If `atlas.json`'s `template` path does not exist there, it builds only `ATLAS.md`.
