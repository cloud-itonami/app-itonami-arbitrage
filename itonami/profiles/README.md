# itonami/profiles — the itonami agent profiles this repository runs as

This directory is the **source of truth** for the itonami agent profiles
(`kotoba-lang/itonami-agent`) that act on behalf of this repository. An
itonami agent is not a Hermes agent: its store, state and inference rail stay
separate (ADR-2610222100 in `com-junkawasaki/root`; the Two CLIs table in
`kotoba-lang/itonami-agent/AGENTS.md`). This repository has no Hermes profile.

| | place in repo | host store | inference |
|---|---|---|---|
| itonami agent | `itonami/profiles/<name>/` | `~/.itonami/profiles/<name>/` (`ITONAMI_DIR`) | `itonami.edn :inference`: murakumo only |

```
itonami/profiles/<profile>/
  itonami.edn      cloud.itonami.profile.v2: rail, placement, scheduler, bundle CID
  yakuwari.edn     the profile's capabilities (the authority; itonami.edn copies it)
  SOUL.md          the bot's standing instructions
  profile.yaml     one-line description
  config.yaml      model / provider routing (host-local keys removed)
  cron/jobs.json   job definitions only — no run state
  skills/<name>/   skills this bot owns
  scripts/         scripts its cron jobs run
  secrets.edn      which env vars it needs and where they come from — never a value
```

**Never here:** `.env` and any secret value, the measurement ledger and
`workspace/`, sessions, memories, logs, caches, run state.

The registry entry for each profile is in `com-junkawasaki/root`
`manifest/agent-registry.edn` with `:agent/runtime :itonami`. It is not in
`manifest/hermes-profile-repos.edn`, so the root `hermes-profile-repo.cljk`
commands do not apply: do not materialize these profiles into
`~/.hermes/profiles/`, where they would be Hermes profiles on murakumo again.
itonami-agent's own `profile import/export` route is not selfhost-qualified
yet, so placing a profile on a host is a separate, owner-approved step.

## Check

With the itonami-agent Otehon CLI (bb, nbb and Basilisp give the same result):

```
otehon/bin/itonami-otehon bb check <this repo>/itonami/profiles/awai-arb
```

After editing SOUL, config, jobs, scripts or a skill, recompute the bundle CID
with `profile refresh-bundle <name>` on a store copy (`ITONAMI_DIR`) and copy
the CID back into `itonami.edn`. The check does not detect a stale CID.

## Profiles

| profile | what it does | cron |
|---|---|---|
| `awai-arb` | measures arbitrage surfaces (torihiki devnet, x402.nexus, murakumo pricing, Coinbase refs) into an append-only ledger, drafts proposals from it, and sends them to the ossekai intake. Propose-only; never trades. Defined only: not placed on a host, cron not started. | `awai-arb-measure` every 30m (script), `awai-arb-ossekai-report` every 6h (agent, drafts only), `awai-arb-propose-post` every 30m (script, POST + read-back) |
