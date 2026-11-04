# HANDOVER.md

Överlämning mellan agenter och sessioner. Läs innan du börjar, uppdatera innan du slutar.

## Aktuellt läge

*Senast inventerat 2026-11-04 av Claude (Cowork).*

Projekt: RouteDoctor explains **why a routing table selects a path** and highlights common forwarding failures before they become long troubleshooting sessions.

- Huvudbranch: `main`
- Senaste commit på `main`: 2026-11-01 `a500ec6` Add privacy guard for local and CI scans (#2)
- Öppna PR:er: 0
- Andra brancher på remote: 2

## Pågående arbete

| Agent/vem | Branch | Status | Beskrivning |
|-----------|--------|--------|-------------|
| Cursor | `cursor/privacy-guard-8915` | branch utan PR, senaste commit 2026-11-01 | Add privacy guard for local and CI scans |
| okänd (människa/agent) | `agent/route-analysis-mvp` | branch utan PR, senaste commit 2026-07-18 | Document RouteDoctor routing analysis |

## Nästa steg

- Gå igenom brancher utan PR: öppna PR, merga eller radera (fråga användaren innan radering).
- Fyll på "Bygga och testa" i AGENTS.md om något saknas eller är fel.

## Kända problem

- Inga dokumenterade ännu.

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
