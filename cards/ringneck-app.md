---
id: a-4b90d2
title: Ringneck app (oinkr)
kind: app
host: vercel
where: "Vercel project ringneck-pork (team code-harvest): drove.farm, oinkr.ai, https://ringneck-pork.vercel.app"
what: The Ringneck Next.js app, built from the repo root. Also runs the Monday packet cron (Mondays 17:00 UTC).
why: Ringneck Pork's production app; daily production use.
source: ~/Developer/ringneck-pork (repo root; vercel.json holds the cron)
entry: https://www.drove.farm
check: curl -fsS -o /dev/null -m 10 https://www.drove.farm
links: [a-19d6ef, a-c3157a, a-7e21c4]
notes: []
confidence: believed
confirmed: 2026-10-22
---

## Short version

Vercel project `ringneck-pork`, Next.js at the repo root. Domains `drove.farm` (redirects to `www.drove.farm`) and `oinkr.ai`. This is the project the local checkout is linked to.

## Untangled

- Production deploys are rare: 1 of the last 50 GitHub deployments (commit 8b91edf, Oct 21). Most pushes make a Preview here and a Production deploy of the billing site.
- `vercel.json` at the repo root defines `/api/cron/monday-packet` at `0 17 * * 1`. The root belongs to this project, so the cron is believed to run here; not yet confirmed in the Vercel dashboard.

## To change it

Work in `~/Developer/ringneck-pork`, push to `main`, then check whether production was promoted (`vercel ls ringneck-pork`).

## Gotchas

Production does not appear to follow `main` automatically. Confirm with Clark how a release gets promoted.
