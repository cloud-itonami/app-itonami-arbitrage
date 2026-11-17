# hermes/ — the resident bots this repository runs as

This directory is the **source of truth** for the Hermes profiles that act on
behalf of this repository. A profile lives here, not in `~/.hermes/profiles/`:
the host directory is materialized from this tree and checked against it.

```
hermes/profiles/<profile>/
  SOUL.md          the bot's standing instructions
  profile.yaml     one-line description
  config.yaml      model / provider routing (host-local keys removed)
  cron/jobs.json   job definitions only — no run state
  skills/<name>/   skills this bot owns (the generic bundled skills are not copied)
  scripts/         scripts its cron jobs run
```

`secrets.edn` (optional) declares which environment variables the bot needs and
where each comes from — a kagi item or a 1Password `op://` reference, never a
value. `hermes-profile-repo.cljk secrets <profile>` writes the host's `.env` from it.

**Never here:** `.env` and any secret value, the measurement ledger and
`workspace/`, sessions, memories, logs, caches, run state. Secrets are placed
on the host from kagi (ADR-2607198200); run data stays on the host.

Materialize / check / export from the superproject root
(`scripts/hermes-profile-repo.cljk`, registry `manifest/hermes-profile-repos.edn`):

```
kbb --backend sci scripts/hermes-profile-repo.cljk materialize awai-arb   # repo -> host
kbb --backend sci scripts/hermes-profile-repo.cljk check awai-arb         # compare only
kbb --backend sci scripts/hermes-profile-repo.cljk export awai-arb        # host -> repo
```

`check` exits 0 when host and repo agree, 1 on drift (named per file), 2 when
it could not compare (a `REFUSE` line says why). Edits the bot makes to its
own SOUL or skills on the host show up as drift; `export` brings them back to
be committed here. `materialize` keeps the host's own config blocks (secrets
helper, allowlist, terminal cwd) and cron run state, and does not invent cron
jobs the host lacks — it prints `NEEDS-REGISTER` for them.

## itonami agent profile (awai-arb, since 2026-11-18)

`awai-arb` uses the murakumo rail, so it is an **itonami agent** profile, not
a Hermes one (owner decision 2026-11-18, AWAI-3213; the Two CLIs table in
`kotoba-lang/itonami-agent/AGENTS.md`). The Hermes layout above is unchanged;
two files are added:

```
  itonami.edn      cloud.itonami.profile.v2: murakumo rail, deny openrouter.ai,
                   local placement, itonami scheduler, bundle CID
  yakuwari.edn     the profile's capabilities (propose-only; trades, funds,
                   publish and git writes blocked; email_send needs approval)
```

Its host store is `~/.itonami/profiles/awai-arb/` (`ITONAMI_DIR`), not
`~/.hermes/profiles/`. The `hermes-profile-repo.cljk` commands above still
target the Hermes store, and itonami-agent's own `profile import/export` route
is not selfhost-qualified yet, so placing this profile on a host is a separate
step. Do not materialize it into `~/.hermes/profiles/`: there it would be a
Hermes profile on murakumo again.

Check it with the itonami-agent Otehon CLI (bb, nbb and Basilisp give the same
result):

```
otehon/bin/itonami-otehon bb check <this repo>/hermes/profiles/awai-arb
```

After editing SOUL, config, jobs, scripts or the skill, recompute the bundle
CID with `profile refresh-bundle awai-arb` on a store copy and copy the CID
back into `itonami.edn`.

## Profiles

| profile | what it does | cron |
|---|---|---|
| `awai-arb` (itonami) | measures arbitrage surfaces (torihiki devnet, x402.nexus, murakumo pricing, Coinbase refs) into an append-only ledger, drafts proposals from it, and sends them to the ossekai intake. Propose-only; never trades. | `awai-arb-measure` every 30m (script), `awai-arb-ossekai-report` every 6h (agent, drafts only), `awai-arb-propose-post` every 30m (script, POST + read-back) |
