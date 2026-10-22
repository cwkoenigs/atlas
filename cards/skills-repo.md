---
id: a-3e8c61
title: Skills repo
kind: repo
host: github
where: github.com/cwkoenigs/skills (private); ~/Developer/skills
what: Every skill available to Clark, readable in one place, plus the new-Mac installer.
why: To see what skills exist and carry them to another Mac.
source: ~/Developer/skills/skills (Hermes skills.create_dir); refresh.py rebuilds the copies and INDEX.md
entry: open ~/Developer/skills/INDEX.md
check: hermes config get skills.create_dir 2>/dev/null | grep -q Developer/skills/skills
links: [a-0a71a5]
notes: []
confidence: confirmed
confirmed: 2026-10-22
---

## Short version

New skills Hermes writes land here. Run `python3 refresh.py --commit` and push after changes.

## Untangled

`personal-tax-prep`, `finance-hub` and `kids-school-tracker` stay in `~/.hermes/skills` on purpose (`local-only.txt`).

## To change it

## Gotchas
