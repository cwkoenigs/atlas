---
id: a-d15a4e
title: dashboard-style package
kind: repo
host: github
where: github.com/cwkoenigs/dashboard-style; ~/Developer/dashboard-style
what: The Data Science design system packaged for dashboards: theme, templates, two skills.
why: Every dashboard (life-admin, atlas) is styled from it, so a design change reaches all of them.
source: ~/Developer/dashboard-style/theme/dashboard.css and design-system/tokens.json
entry: make -C ~/Developer/dashboard-style build check
check: test -f ~/Developer/dashboard-style/templates/dashboard.html
links: [a-b7d302]
notes: []
confidence: confirmed
confirmed: 2026-10-22
---

## Short version

After a CSS change: `make build check`, then `python3 scripts/build_theme.py --into` the pages.

## Untangled

## To change it

Edit `theme/dashboard.css` (var() tokens only), `make build check`, commit, push.

## Gotchas
