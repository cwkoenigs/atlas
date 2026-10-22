---
id: a-7e21c4
title: Ringneck billing site
kind: site
host: vercel
where: Vercel project ringneck-billing (team code-harvest), https://ringneck-billing.vercel.app
what: The billing site. Builds from site/ringneck-billing in the ringneck-pork repo.
why: Ringneck Pork's billing pages; it is the project that gets a production deploy on every push to main.
source: ~/Developer/ringneck-pork/site/ringneck-billing (GitHub cwkoenigs/ringneck-pork, main)
entry: https://ringneck-billing.vercel.app
check: curl -fsS -o /dev/null -m 10 https://ringneck-billing.vercel.app
links: [a-19d6ef, a-4b90d2]
notes: []
confidence: confirmed
confirmed: 2026-10-22
---

## Short version

One GitHub repo feeds two Vercel projects. This one is `ringneck-billing`: Vercel's root directory is `site/ringneck-billing`, framework "Other". A push to `main` deploys it to production.

## Untangled

- Looked like: the repo is "the website", deployed by the `.vercel` link in the checkout.
- Actually: the checkout's `.vercel/project.json` links to the *other* project (`ringneck-pork`). This project is configured on Vercel itself, with its root set to `site/ringneck-billing`.
- How we know: `vercel project inspect ringneck-billing` shows the root directory; GitHub deployments show 9 of the last 50 as "Production – ringneck-billing", the latest for commit db61b32 on Oct 22.

## To change it

Edit `site/ringneck-billing/` in `~/Developer/ringneck-pork`, push to `main`. Watch it with `vercel ls ringneck-billing` from that folder.

## Gotchas

`vercel` commands run in the checkout target `ringneck-pork` by default, because of the `.vercel` link. Name the project explicitly.
