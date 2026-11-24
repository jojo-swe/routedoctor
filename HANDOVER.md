# HANDOVER.md

Överlämning mellan agenter och sessioner. Läs innan du börjar, uppdatera innan du slutar.

## Aktuellt läge

*Senast uppdaterat 2026-11-24 av Claude Code.*

Projekt: RouteDoctor explains **why a routing table selects a path** and highlights common forwarding failures before they become long troubleshooting sessions.

- Huvudbranch: `main`
- Senaste commit på `main`: 2026-11-01 `a500ec6` Add privacy guard for local and CI scans (#2)
- Version 1.0.0 är implementerad på `agent/claude/v1` (IPv6, IOS- och Linux-parsers, `--format`, `--trace-from`, `routedoctor.web.run`, demo-manifest). README och CHANGELOG är uppdaterade. Taggen `v1.0.0` är inte satt.
- Öppna PR:er: 1 (från `agent/claude/v1`, öppnas av kontrollanten)
- Andra brancher på remote: 2

## Pågående arbete

| Agent/vem | Branch | Status | Beskrivning |
|-----------|--------|--------|-------------|
| Claude Code | `agent/claude/v1` | 1.0 implementerad, PR öppen, taggen väntar på grön CI | IPv6, textparsers, trace, webb-ingång, demo-manifest och dokumentation för 1.0 |
| Cursor | `cursor/privacy-guard-8915` | branch utan PR, senaste commit 2026-11-01 | Add privacy guard for local and CI scans |
| okänd (människa/agent) | `agent/route-analysis-mvp` | branch utan PR, senaste commit 2026-07-18 | Document RouteDoctor routing analysis |

## Nästa steg

- Merga PR:en från `agent/claude/v1`.
- Tagga `v1.0.0` och skapa GitHub-release när CI är grön på `main`.
- Avgör vad som ska hända med de gamla brancherna `cursor/privacy-guard-8915` och `agent/route-analysis-mvp` (öppna PR, merga eller radera; fråga användaren innan radering).
- Webbdemon på https://johnjohansson.com/lab/routedoctor/ är planerad men inte publicerad.

## Kända problem

- VRF stöds inte.
- `--trace-from` kräver enhetens egna adresser: IOS `L`-rutter ger dem, för Linux måste de anges i JSON.
- Länklokala IPv6-next hops behandlas som direktanslutna via sitt gränssnitt och kan inte följas till en annan enhet.
- Endast IOS och Linux som textformat.

## Senaste commits

- 2026-11-01 `a500ec6` Add privacy guard for local and CI scans (#2)
- 2026-10-26 `6606ca6` docs: add contributor guide
- 2026-10-26 `57443d7` docs: add failure example, limitations, and CI badge to README
- 2026-10-26 `3617ba7` feat: support running as python -m routedoctor
- 2026-10-26 `0681fbd` chore: add Apache 2.0 license text
- 2026-10-26 `e1d3621` feat: report inactive routes skipped for a destination
- 2026-10-26 `4c4acef` feat: report equal-cost paths instead of a false tie-break
- 2026-10-26 `d36eb69` fix: restore green CI by pinning ruff rules and dropping stale test
- 2026-07-20 `eb6bef2` Merge pull request #1 from jojo-swe/agent/route-analysis-mvp
- 2026-07-18 `8008217` Document RouteDoctor routing analysis

## Logg

| Datum | Agent | Vad som gjordes |
|-------|-------|-----------------|
| 2026-11-04 | Claude (Cowork) | Lade till AGENTS.md, HANDOVER.md och CLAUDE.md; inventerade PR:er, brancher och commits. |
| 2026-11-24 | Claude Code | Version 1.0.0: README, CHANGELOG, versionshöjning, demo-manifest och två nya CI-steg (IOS-fixture, loop-trace). Branch `agent/claude/v1`. |
