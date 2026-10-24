---
id: a-0a71a5
title: Atlas
kind: repo
host: this-mac
where: ~/Developer/atlas
what: "This map: one card per thing that runs somewhere, a wiki built from them, and the atlas command."
why: So an hour of untangling ends up somewhere Clark can find it again.
source: "~/Developer/atlas: cards/ and the Python package src/atlas_cli (GitHub cwkoenigs/atlas)"
entry: atlas in a terminal; atlas wiki opens http://localhost:8788
check: test -x ~/.local/bin/atlas && git -C ~/Developer/atlas rev-parse --git-dir >/dev/null
links: [a-3e8c61, a-b7d302]
notes: []
confidence: confirmed
confirmed: 2026-10-22
---

## Short version

Morning: `atlas` in a terminal, or `atlas wiki` for the wiki in the browser (also the life-admin hub's Atlas tile). After untangling something: ask Hermes to distill it into a card (the atlas skill).

## Untangled

- The `atlas` command is the Python package in `src/atlas_cli`, installed with `uv tool install --editable`; `/opt/homebrew/bin/atlas` and `atlast` are shims to `~/.local/bin/atlas`. The old `bin/atlas` script is gone.
- The wiki is served by that package on 127.0.0.1:8788. `atlas` and `atlas wiki` start it when it is down and restart it after the code changes. It is not a launchd job.
- Page history lives in `.state/history/`, on this Mac only.

## To change it

Edit the cards (in the wiki, or the files in `cards/`, `inbox/`, `retired/`); change the code in `src/atlas_cli` and push. The wiki picks up code changes on the next `atlas`.

## Gotchas

`~/Documents/life-admin/atlas.html` only forwards to the wiki; it shows how to start the wiki when it is not running.
