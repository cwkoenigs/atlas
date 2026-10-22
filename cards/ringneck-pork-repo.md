---
id: a-19d6ef
title: ringneck-pork repo
kind: repo
host: github
where: github.com/cwkoenigs/ringneck-pork; working checkout ~/Developer/ringneck-pork
what: Source for the Ringneck app, the billing site, and the Inv Mon automation.
why: Client work for Ringneck Pork (CodeHarvest's main client).
source: ~/Developer/ringneck-pork, branch main
entry: cd ~/Developer/ringneck-pork
check: git -C ~/Developer/ringneck-pork rev-parse --is-inside-work-tree >/dev/null && test -f ~/Developer/ringneck-pork/.vercel/project.json
links: [a-7e21c4, a-4b90d2, a-e84b17, a-5a0e83]
notes: []
confidence: confirmed
confirmed: 2026-10-22
---

## Short version

Work in `~/Developer/ringneck-pork`. It is the checkout linked to Vercel and the one the Inv Mon job runs in. `~/code/ringneck-pork` is an older clone.

## Untangled

- Looked like: two checkouts, both with `vercel.json`, either could be "the one".
- Actually: both point at the same GitHub repo. `~/Developer` has 445 commits (latest db61b32, Oct 22) and the `.vercel` link; `~/code` stops at 5c71a0d (Oct 15), 185 commits behind.
- Vercel builds from GitHub, not from either folder, so "which folder serves the site" is really "which branch and which Vercel project": `main`, two projects (see links).

## To change it

Commit and push from `~/Developer/ringneck-pork`.

## Gotchas

The CodeHarvest dashboard still links `~/code/ringneck-pork` as the real repo.
