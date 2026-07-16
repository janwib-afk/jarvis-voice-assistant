# Phase 4B — Action als deep module (Umsetzung von RFC-0001)

> Stand 2026-07-15. Umsetzung von [RFC-0001](RFC-0001-action-deep-module.md)
> (`Accepted for incremental implementation`, **Variant A**). Folgt gemäß D1
> **nach** dem Composition Root ([RFC-0002](RFC-0002-composition-root.md),
> [Phase 4A](PHASE4_COMPOSITION_ROOT_MIGRATION.md), gemergt als `b8d25c6`).

## Ausgangszustand

Das Wissen über eine Action war dreifach repräsentiert und über zwei Module
verstreut:

| Repräsentation | Ort (vorher) |
|---|---|
| Metadaten | `actions.ActionSpec` + `REGISTRY` |
| Verhalten | `assistant_core.execute_action` — `if/elif` mit **22** Zweigen |
| Prompt-Beschreibung | hardcodierter Text in `assistant_core.build_system_prompt` |

Bestätigt am Code vor dem Umbau: **22 registrierte Typen**, **22 Ausführungszweige**,
`parse_action` als bestehender permanenter Adapter, `execute_action` als Dispatcher,
`build_system_prompt` als zweite Beschreibungsquelle. Baseline vor dem Umbau grün
(525 Tests, Smoke 0 Skips).

> **Evidenz-Korrektur:** RFC-0001 nannte „24 Zweige". Das war veraltete Evidenz —
> der tatsächliche Vertrag umfasst **22**. Korrigiert wurde nur diese Zahl, nicht
> die akzeptierte Architekturentscheidung.

## Öffentliche Seam

```python
spec = actions.spec_for(TYP)                  # Registry-Eintrag
result = await spec.execute(payload, ctx)     # Ausführung  -> rohes Ergebnis
text   = spec.describe(prompt_ctx)            # Selbstbeschreibung (None = nicht beworben)
block  = actions.render_action_block(prompt_ctx)   # Prompt-Block aus der Registry
```

**`ActionContext`** (frozen, request-scoped) — bewusst winzig:

| Feld | Zweck |
|---|---|
| `ai` | LLM-Zugriff (prod: Anthropic, test: Fake) — der einzige echte Seam |
| `history` | **unveränderlicher Snapshot** des Sitzungsverlaufs |
| `persist_launcher` | optionaler async Hook für Launcher-Persistenz |

**Nicht** im Kontext: `session_id`, `conversations`-Dict, `Runtime`, HTTP-Client,
Browser-/Memory-/Launcher-/Screen-/Clipboard-Service. Die Capability-Module sind
**direkte** Abhängigkeiten der Implementation (RFC-0001: ein zusätzlicher Port wäre
hypothetisch — „one adapter = hypothetical, two = real").

**`PromptContext`** (frozen): `user_name`, `user_address`, `app_names`, `profile_names`.

## Slices, Rot-/Grün-Evidenz und Rollbackpunkte

| Slice | Commit | Rot (Beleg) | Grün | Rollbackpunkt |
|---|---|---|---|---|
| **0** Seam + Shim + SESSION_SUMMARY | `d8a01de` | `AttributeError: 'ActionSpec' object has no attribute 'execute'` | 527 Tests | Commit reverten; Legacy-`if/elif` war unangetastet |
| **1** Browser (SEARCH, BROWSE, OPEN, NEWS, RESEARCH) | `5ca9e3d` | je Action rot vor der Verschiebung (4 Klassen `FAILED (errors=…)`) | 537 Tests | Commit reverten → Zweige zurück |
| **2** Memory/Vault (7 Actions) | `7ce531a` | 6 Klassen rot | 551 Tests | Commit reverten |
| **3** Launcher (6 Actions) | `48e32bd` | 5 Klassen rot | 567 Tests | Commit reverten |
| **4** SCREEN, CLIPBOARD, CLIPBOARD_NOTE | `df14c00` | 3 Klassen rot | 574 Tests | Commit reverten |
| **P** Prompt aus der Registry | `ce63713` | `render_action_block` existierte nicht (5 Tests rot) | 586 Tests | Commit reverten → hardcodierter String |
| **P-Fix** Golden-Reader | `9f1e69e` | CRLF-Checkout reproduzierbar ungleich | 586 Tests | Commit reverten |
| **C** Legacy-Cleanup | `5df170b` | — (reine Entfernung nach grünem Gate) | 586 Tests | Commit reverten → Shim zurück |
| **Tests** auf die Seam | `140f62e` | 2 Persist-Tests rot nach Umstellung | 589 Tests | Commit reverten |

Jeder Slice ist einzeln revertierbar; **kein Zweig wurde kopiert** — die Zweigkörper
wurden *verschoben*, es gab zu keinem Zeitpunkt zwei Ausführungsquellen für dieselbe
Action. Parität wurde nie durch reale doppelte Ausführung geprüft (spezifikationsbasierte
Erwartungen + kontrollierte Fakes/Temp-Verzeichnisse).

## 22/22-Migrationsmatrix

| # | Action | Slice | beworben | Ausführung |
|---|---|---|---|---|
| 1 | SEARCH | 1 | ✅ (1) | `_exec_search` |
| 2 | RESEARCH | 1 | ✅ (2) | `_exec_research` |
| 3 | OPEN | 1 | ✅ (3) | `_exec_open` |
| 4 | SCREEN | 4 | ✅ (4) | `_exec_screen` |
| 5 | NEWS | 1 | ✅ (5) | `_exec_news` |
| 6 | INBOX_READ | 2 | ✅ (6) | `_exec_inbox_read` |
| 7 | INBOX_WRITE | 2 | ✅ (7) | `_exec_inbox_write` |
| 8 | MEMORY_WRITE | 2 | ✅ (8) | `_exec_memory_write` |
| 9 | MEMORY_READ | 2 | ✅ (9) | `_exec_memory_read` |
| 10 | MEMORY_FORGET | 2 | ✅ (10) | `_exec_memory_forget` |
| 11 | NOTES_RECENT | 2 | ✅ (11) | `_exec_notes_recent` |
| 12 | PROJECT_CONTEXT | 2 | ✅ (12) | `_exec_project_context` |
| 13 | CLIPBOARD | 4 | ✅ (13) | `_exec_clipboard` |
| 14 | CLIPBOARD_NOTE | 4 | ✅ (14) | `_exec_clipboard_note` |
| 15 | SESSION_SUMMARY | **0** | ✅ (15) | `_exec_session_summary` |
| 16 | APP_OPEN | 3 | ✅ (16, launcher) | `_exec_app_open` |
| 17 | PROFILE_ACTIVATE | 3 | ✅ (17, launcher) | `_exec_profile_activate` |
| 18 | PROFILE_STATUS | 3 | ✅ (18, launcher) | `_exec_profile_status` |
| 19 | APP_AUTOSTART_ON | 3 | ✅ (19, launcher) | `_exec_autostart_on` |
| 20 | APP_AUTOSTART_OFF | 3 | ✅ (20, launcher) | `_exec_autostart_off` |
| 21 | APP_PLACE | 3 | ✅ (21, launcher) | `_exec_app_place` |
| 22 | **BROWSE** | 1 | ❌ **bewusst nicht** | `_exec_browse` |

**22/22 ausführbar** (`spec.execute is not None`), **21/22 beworben**. `BROWSE` ist
registriert und ausführbar, war aber noch nie im System-Prompt — `describe=None` hält
das fest, statt es unbemerkt neu zu bewerben.

## Prompt-Golden-Evidenz

Zwei byte-genaue Fixtures wurden **vor** der Produktionsänderung aus dem damaligen
Verhalten aufgezeichnet und werden **nie** automatisch neu erzeugt:

| Fixture | Inhalt | Größe |
|---|---|---|
| `tests/fixtures/prompt_golden/system_prompt_with_apps.txt` | deterministische Config **mit** Apps + Profilen | 7577 Zeichen |
| `tests/fixtures/prompt_golden/system_prompt_without_apps.txt` | deterministische Config **ohne** Apps | 5827 Zeichen |

Der **vollständige** System-Prompt ist gegen beide byte-identisch. Zusätzlich
abgesichert: heutige Reihenfolge (1–21, deklarativ über `prompt_order` — kein Iterieren
in Registry-Reihenfolge), Launcher-Gruppe inkl. gemeinsamem Regel-Suffix nur bei
konfigurierten Apps, `BROWSE` nicht im Block, und `build_system_prompt` enthält keine
`[ACTION:`-Zeile mehr. Kein Prompt-Text wurde sprachlich geändert, korrigiert oder
umformatiert.

> **Gefundener Fehler (P-Fix `9f1e69e`):** Das Repo läuft mit `core.autocrlf=true` ohne
> `.gitattributes` — ein frischer Checkout (Hosted-Runner) liefert die Fixtures mit
> **CRLF**, der Prompt selbst enthält nur `\n`. Der ursprüngliche Reader (`newline=""`)
> hätte den Golden-Vergleich dort rein zeilenende-bedingt rot gemacht; nachgewiesen per
> CRLF-Simulation, behoben durch Universal-Newline-Lesen. Beide Varianten sind belegt grün.

## Erhaltene Verträge

- **22 Action-Typen**, heutige Typ-Strings, Metadaten, Payload-Regeln, Risk, Timeout
  und alle abgeleiteten Sets (`CONFIRM_ACTIONS`, `SPEAK_RESULT_ACTIONS`, `URL_ACTIONS`,
  `BROWSER_ACTIONS`, `PAYLOAD_/NO_PAYLOAD_/OPTIONAL_PAYLOAD_ACTIONS`) — per Test geschützt.
- **`[ACTION:…]`-Wire-Format**, `ACTION_PATTERN`, `parse_action`-Rückgabeformat,
  URL-Normalisierung und die http/https-Grenze: unberührt.
- **MEMORY_FORGET-Confirmation**: unverändert **außerhalb** der Action.
- **Stop/Cancel**: `CancelledError` schlägt durch `execute` durch (per Test belegt).
- **REST-/WS-Formate**, **Config-/Memory-Dateiformate**: unverändert.
- **APP_OPEN-Allowlist**, keine Shell-Ausführung aus Modelltext: unverändert.
- **Direkte Sprachausgabe** der sechs Launcher-Actions, **OPEN** ohne
  Zusammenfassungs-LLM, **RESEARCH** mit Quellenanzeige + Autosave: unverändert.
- **Entry Points** (`server.app`, `uvicorn server:app`, `python server.py`, Launcher),
  **Composition-Root-Besitz** und **Lifespan**: unberührt.
- **Import-Sicherheit**: `actions.py` importiert die Capability-Module, erzeugt beim
  Import aber weiterhin keine Config-I/O, Clients, Browser, Screens oder
  Clipboard-Zugriffe (Composition-Root-Tests belegen es).

## Bewusst verbleibende Orchestrierung

`run_action_and_respond` bleibt unverändert außen und besitzt weiterhin: Timeout
(`asyncio.wait_for(…, spec.timeout)`), Cancellation/Stop, Confirmation, WS-Events,
TTS, Ergebniszusammenfassung, `speaks_result`-Zweig, **OPEN-Frühabbruch**,
**SCREEN-Sprachfeedback** und **RESEARCH-Autosave** inkl. Quellenanzeige
(`_finish_research`). Diese drei Stellen prüfen weiterhin `action.type` — das ist
**kein** Dispatch, sondern die von RFC-0001 ausdrücklich außen gehaltene Orchestrierung.

`assistant_core.execute_action(action, session_id)` bleibt als kompatibler **Thin
Dispatcher**: Kontext bauen, Registry-Lookup, `await`.

## Testevidenz (lokal, frisch)

| Prüfung | Ergebnis |
|---|---|
| `tests/test_action_deep_module.py` (neu) | grün — 22/22 Ausführung, Beschreibung, Goldens, Dispatcher, Cancellation |
| Volle Unittest-Suite | **589 Tests, OK** (Baseline vorher 525) |
| `scripts/smoke-test.py` | grün, **0 unerwartete Skips** |
| Browser-Flows · A11y · Reduced Motion · **Visual (ohne Baseline-Update)** | grün |
| Native · `verify_phase4` · `verify_phase5` | grün |

Keine echten Provider, keine persönliche Config, keine echten Apps/Screens/Clipboards,
keine kostenpflichtigen Aufrufe. Dateisystemtests ausschließlich in Temp-Verzeichnissen.

## Ausdrücklich NICHT umgesetzt (spätere Phasen)

- **Capability-/Policy-Lifecycle** (`validate/preview/authorize/verify`) — Phase 5.
  Dieses RFC schafft nur den Seam, an dem das andockt.
- Protokoll-Versionierung (`protocol_version`/`event_id`/`correlation_id`),
  State Machines, Config-Schema-Migration, strukturierte Logs, Job-Engine/Scheduler/
  Outbox/Saga.
- **K03** (Conversation-Session-Besitz), **K04** (Provider-Deepening),
  **K05** (Settings-Single-Writer), **D4** (per-App-Browser).
- `[ACTION:…]` bleibt der **permanente** Legacy-Adapter — kein Entfernungskandidat.
- Phase 5 wurde nicht vorgezogen.
