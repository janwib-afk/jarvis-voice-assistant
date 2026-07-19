# Phase 5C — Vollmigration der durchsetzbaren Capability-Pfade (Prompt 20)

> Testgetriebenes Migrationsledger zu **RFC-0007 Amendment 2**. Ein Abschnitt je Slice:
> Ziel und öffentlicher Seam · Ausgangsverhalten · erstes beobachtetes ROT · minimales GRÜN ·
> Regressionsergebnis · Commit-SHA · Rollback-Pfad · offene Restrisiken.

## Rahmen

| | |
|---|---|
| **Basis-SHA** | `96bcc6e68434ddcc06b9897a0df4cfdb5734769f` (Merge-Commit aus Prompt 19, zwei Eltern) |
| **Branch** | `phase-5c-capability-full-migration`, direkt von `origin/master` |
| **Amendment** | RFC-0007 Amendment 2, angenommen 2026-07-19 durch den Nutzer |
| **Vorgänger-Ledger** | `PHASE5B_CAPABILITY_POLICY_KERNEL_MIGRATION.md` (Prompt 19, Slices 0–10) |

### Start-Gate (read-only, vor jeder Dateiänderung)

| Prüfung | Ergebnis |
|---|---|
| `origin/master` | `96bcc6e6…` — exakt |
| Merge-Eltern | `f03e4d63…` + `99815a22…` — zwei |
| Post-Merge-Lauf `29689663484` | `success`, `workflow_dispatch`, headSha `96bcc6e6…` |
| Fast-Job `88200038084` | `success` |
| Browser-Job `88200038078` | `success` |
| Actions in `actions.REGISTRY` | **22**, davon 2 migriert (`SEARCH`, `MEMORY_FORGET`), **20 offen** |
| Mutierende REST-Routen | **10** (9× `POST`, 1× `DELETE`), Rename migriert, **8 migrierbar**, Delete = Ausnahme |
| Activate-Bypass | `assistant_core.py:431-432` — `await asyncio.to_thread(refresh_data)` |
| Gespeichertes `risk` | `actions.py:88` (Feld), `actions.py:629` (`CONFIRM_ACTIONS` daraus abgeleitet) |
| Legacy-Fallback | `assistant_core.py:342` — `asyncio.wait_for(execute_action(...))` |

### Unveränderte Nutzerartefakte

41 Einträge im Arbeitsbaum sind **ausschließlich** Nutzerartefakte und werden von keinem Slice
angefasst oder gestaged: `.claude/settings.local.json` (modifiziert), `.agents/`,
`.claude/skills/`, `.hermes/`, `.impeccable/`, `skills-lock.json` sowie die lokalen
Screenshot-/Evidenz-/Baseline-Verzeichnisse unter `docs/`.

Der Branchwechsel war nachweislich gefahrlos: `git diff HEAD origin/master` war leer, der Baum
also identisch — keine Nutzeränderung konnte überschrieben werden. Es wurde **kein** `git stash`,
`git reset --hard`, `git clean`, `git add .` oder `git add -A` verwendet; jeder Commit stagt
ausschließlich explizit aufgezählte Pfade.

### Baseline vor Produktivänderungen

| Gate | Ergebnis |
|---|---|
| `python -m unittest discover -s tests` | **1024 Tests, OK** |
| `verify_phase4` | **27/27** |
| `verify_phase5` | **13/13** |
| Fixture-Set-SHA256 (4 Dateien) | `dd770c19cc24fae8a52807220ad134b48b605085c14e40dda857dd0c2f1f3b55` |

Die Baseline ist grün — `PROMPT 20 BLOCKIERT – BASELINE ROT` trifft nicht zu.

Die Verifier laufen gegen den lokalen Harness `docs/design-baseline/tools/baseline_server.py` auf
**Port 8341**. **Port 8340 ist von der echten Jarvis-Instanz des Nutzers belegt und wird zu keinem
Zeitpunkt beendet**; es wurden ausschließlich eigene Testprozesse gestoppt.

---

## Slice 0 — Amendment 2, Baseline und Ledger

**Ziel und Seam.** Den in Amendment 1 belegten Scope-Widerspruch förmlich auflösen und die
Vertragsvertiefungen beschließen, bevor Produktionscode entsteht. Kein Produktionscode in diesem
Slice.

**Ausgangsverhalten.** RFC-0007 kündigte an zwei Stellen (`:792`, `:802`) die Migration von
**neun** REST-Routen in Prompt 20 an, während Amendment 1 §A1.4 (`:901-903`)
`launcher.profile.delete` bis Phase 10 unverändert lässt. Beides ist nicht gleichzeitig erfüllbar.

**Geändert.**
* `docs/architecture/RFC-0007-capability-policy-kernel.md` — Amendment 2 (§A2.1–A2.10) angehängt;
  die widersprüchliche Stelle `:792` trägt jetzt einen expliziten Korrekturhinweis auf §A2.1.
* `docs/architecture/PHASE5C_CAPABILITY_FULL_MIGRATION.md` — dieses Ledger.

**Rollback.** `git revert` dieses Commits; da kein Produktionscode betroffen ist, bleibt die
Laufzeit unberührt.

**Restrisiko.** Keines — reine Dokumentation.
