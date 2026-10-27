# Empty-by-default installation

The application repository must contain no inventory and must not assume the home-machine dashboard or host list exists. Inventory and machine-specific configuration are local data, not application code.

## Changes

- Removed nine previously tracked cards from the current Git tree. Existing home files are preserved separately during deployment; this is not an instruction to delete the home inventory.
- Ignore the complete `cards/`, `inbox/`, and `retired/` trees plus `atlas.local.json`, rather than only personal subdirectories.
- Ship one neutral place (`this-mac`: This computer); disable external HTML output and dashboard-template lookup by default.
- Load optional ignored `atlas.local.json` over portable defaults. Keys replace entire values, including the host map. The home computer can retain its integration there without exporting it to another computer.
- Document a shallow clone, standalone installation, local data/backups, optional scanning, and the fact that Git updates application code rather than inventory.

## Observed test-first regressions

1. Exporting the original Git tree loaded nine cards instead of zero. Removing tracked inventory made it pass.
2. Ignore checks initially missed ordinary card folders and local config. The new ignore rules made them pass.
3. The shipped config initially enabled home dashboard export and home host labels. Neutral defaults made it pass.
4. An ignored local config was initially not loaded. The optional overlay made it pass without changing the base file.

5. A wiki request initially discarded local settings by reloading only the base file. A shared loader for initial import and every wiki snapshot made the host/port/check settings persist.

All **124 repository tests pass**, including the five new regressions.

## Actual fresh-install acceptance

The parent made a genuine shallow clone of the candidate, installed it in a separate uv tool environment, and ran the installed command under a fresh HOME with no `ATLAS_DIR`/`PYTHONPATH` overrides and no external dashboard checkout.

- Initial inventory: **zero cards**.
- Ten empty-wiki routes returned working HTML, without home-project article links.
- No Documents/life-admin or dashboard-style folders were needed or created.
- Creating the first local page, rendering it, and running its harmless fixture check all succeeded.
- The resulting page/history/check artifacts stayed ignored; the cloned application working tree stayed clean.
- The fixture server was stopped afterward.

The running home inventory requires a separate preservation gate: backup before updating; retain all card bytes and local history; preserve home integration in ignored local config; verify hashes and parsed metadata after the update before restarting.

## History boundary

Old Git commits still contain the previously committed inventory. This change removes it from the current tree, not from Git history. A fresh `--depth 1` clone does not download that earlier history. No destructive history rewrite or remote record purge was performed.
