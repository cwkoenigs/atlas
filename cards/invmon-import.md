---
id: a-e84b17
title: Inv Mon import
kind: job
host: this-mac
where: "launchd com.ringneck.invmon: Sat and Tue 08:05"
what: Pulls main, then hands automation/invmon/RUNBOOK.md to headless Claude Code to run the inventory import.
why: Keeps Ringneck's inventory monitor data current twice a week without Clark doing it by hand.
source: ~/Developer/ringneck-pork/automation/invmon/ (run_local.sh, RUNBOOK.md); plist in ~/Library/LaunchAgents
entry: ~/Developer/ringneck-pork/automation/invmon/run_local.sh
check: launchctl list com.ringneck.invmon >/dev/null
links: [a-19d6ef]
notes: []
confidence: confirmed
confirmed: 2026-10-22
---

## Short version

A launchd job on this Mac, not a cloud cron. Logs: `~/Library/Logs/invmon/run_<date>.log` (latest Oct 20 08:05).

## Untangled

It runs in `~/Developer/ringneck-pork` (`INVMON_REPO` overrides it). Failures that stop it starting are sent through `notify.sh`.

## To change it

Edit `RUNBOOK.md` for what it does, `run_local.sh` for how it starts, the plist for when.

## Gotchas

It only runs when this Mac is awake at 08:05.
