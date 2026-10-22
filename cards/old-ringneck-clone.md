---
id: a-5a0e83
title: Old ringneck-pork clone
kind: folder
host: this-mac
where: ~/code/ringneck-pork
what: A second, older clone of the ringneck-pork repo, 185 commits behind.
why: None found. Left over from before work moved to ~/Developer on Oct 15. Candidate to retire.
source: Same GitHub repo; nothing unique found here (clean, no local commits)
entry: cd ~/code/ringneck-pork
check: test -d ~/code/ringneck-pork/.git
links: [a-19d6ef, a-b7d302]
notes: []
confidence: believed
confirmed: 2026-10-22
---

## Short version

Not used by anything found so far. Safe to retire once nothing points at it.

## Untangled

`git status` is clean and its HEAD (5c71a0d) is an ancestor of the working checkout's `main`. The Inv Mon job's script says it runs in "the Developer clone (Clark, Oct 15 2026)".

## To change it

To retire: update the CodeHarvest dashboard link, delete the folder, then `atlas retire a-5a0e83 --reason "deleted; work lives in ~/Developer"`.

## Gotchas

`~/code/codeharvest` (client notes) is a different folder and stays.
