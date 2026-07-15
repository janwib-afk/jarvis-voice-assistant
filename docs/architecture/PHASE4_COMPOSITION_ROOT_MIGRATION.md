# Phase 4A — Composition-Root-Migration (Umsetzung von RFC-0002)

> Stand 2026-07-15. Umsetzung von [RFC-0002](RFC-0002-composition-root.md)
> (Status `Accepted for incremental implementation`, inkl. **Amendment 1 —
> voll-lazy Import**, vom Nutzer ausdrücklich akzeptiert). RFC-0001 (Action →
> deep module) bleibt unverändert akzeptiert und folgt **nach** dem Root (D1).

## Checkpoint-Scope — genau 13 Dateien

Der Phase-4A-Checkpoint umfasst **11 fachliche Prompt-8-Dateien** (8 modifiziert,
**3 neu**) plus **2 CI-/Doku-Dateien**, die das Compile-Gate um das neue
Produktionsmodul `runtime.py` ergänzen:

| # | Datei | Art |
|---|---|---|
| 1 | `runtime.py` | **neu** — Composition Root |
| 2 | `server.py` | mod — `APIRouter` + `create_app` + Lifespan |
| 3 | `tests/test_composition_root.py` | **neu** — 18 Tests |
| 4 | `tests/test_config_seam.py` | mod — Lifespan-/Runtime-Migration |
| 5 | `tests/test_dashboard_api.py` | mod — Lifespan-/Runtime-Migration |
| 6 | `tests/test_ws.py` | mod — Lifespan-/Runtime-Migration |
| 7 | `tests/browser/e2e_server.py` | mod — Factory + BORROWED-Fake |
| 8 | `scripts/smoke-test.py` | mod — lifespan-fahrender `TestClient` |
| 9 | `docs/design-baseline/tools/baseline_server.py` | mod — Factory + BORROWED-Fake |
| 10 | `docs/architecture/RFC-0002-composition-root.md` | mod — **Amendment 1** |
| 11 | `docs/architecture/PHASE4_COMPOSITION_ROOT_MIGRATION.md` | **neu** — dieses Dokument (reine Prompt-8-Doku, kein Produktionscode) |
| 12 | `.github/workflows/pr.yml` | mod — nur `runtime.py` in Gate 1 ergänzt |
| 13 | `docs/quality/CI_PIPELINE.md` | mod — nur `runtime.py` in Gate 1 ergänzt |

> **Korrektur:** Der Prompt-8-Abschlussbericht nannte „8 modifizierte + 2 neue Dateien"
> und unterschlug damit dieses Dokument als dritte neue Datei. Korrekt sind **8 + 3**
> fachliche Dateien; mit den beiden CI-/Doku-Dateien ergibt das den 13-Datei-Checkpoint.

## Commit-Strategie — ein atomarer Checkpoint (Abweichung von RFC-0002)

RFC-0002 sah **einen Commit je technischem Slice** vor. Prompt 8 hat die vier Slices
jedoch gemeinsam und uncommitted umgesetzt; die Historie lässt sich nachträglich nur
durch riskantes Hunk-Splitting rekonstruieren — mit dem Ergebnis von Commits, die so
**nie geprüft** wurden. Deshalb bewusst und transparent:

- **Technische Rollback-Grenzen sind je Slice beschrieben** (Tabelle unten) und bleiben
  als Dokumentation gültig — sie sind die Rückrollanleitung, nicht die Git-Historie.
- **Die geprüfte Umsetzung wird als *ein atomarer Phase-4A-Checkpoint* committed** —
  genau der Stand, der lokal und auf dem Windows-Hosted-Runner verifiziert wurde.
- **Spätere Slices erhalten wieder eigene Commits**; die Ein-Commit-Abweichung gilt
  ausschließlich für diesen Nachhol-Checkpoint.

## Ausgeführte Slices

| Slice | Inhalt | Rückrollpunkt |
|---|---|---|
| **1** | `runtime.py` (neu) mit `Runtime`; `server.py`: `create_app(runtime)` + `_server_lifespan`; Import-Bootstrap erzeugt nur eine **ungeöffnete** Runtime; Config-Load/Clients/`configure`/Refresh-Task wandern in `aopen`, Browser-/Client-Close + Task-Cancel in `aclose`; `on_startup`/`on_shutdown`-Hooks und Import-`sys.exit`/Client-Bau entfallen; `__main__` fail-fast | `runtime.py` löschen + `server.py`-Diff reverten |
| **2** | Migration der lifespan-losen Aufrufer auf Lifespan/Factory: `test_config_seam`, `test_ws` (Health), `test_dashboard_api`, `scripts/smoke-test.py`, `tests/browser/e2e_server.py`, `docs/design-baseline/tools/baseline_server.py` | je Datei einzeln revertierbar |
| **3** | Per-App-State (`session_token`, `ws_clients`, `conversations`, `pending_confirm`) im `Runtime`; `wire()` aliast die `assistant_core`-Dicts; neue Isolations- + Lifecycle-Tests (5× flakefrei) | Felder/Tests zurück |
| **4** | E2-Zugriff auf den sicherheitskritischen Pfaden: `_settings_token_ok` und der WS-Endpoint lesen `app.state.runtime` (Token, `ws_clients`, Warnings) statt Modul-Globals | Route-weise zurück |

## Migrierte Zustände und Ressourcen — aktueller Besitzer

| Ressource/Zustand | vorher | **jetzt** |
|---|---|---|
| Config-Laden | Import (`sys.exit` bei Fehler) | **`Runtime.load_config()` im Lifespan** (`aopen`), fails-closed; `__main__` fail-fast vor `uvicorn.run` |
| `ai` (Anthropic), `http` (httpx) | Modul-Global, beim Import erzeugt, **nie geschlossen** | **`Runtime`** — OWNED: im `aopen` erzeugt, im `aclose` geschlossen (Leak behoben); injiziert ⇒ BORROWED |
| Browser (Chromium) | `on_shutdown`-Hook | **`Runtime.aclose`** ruft `browser_tools.close()` (Instanz bleibt modul-globaler Lazy-Singleton — D4-Residual) |
| Refresh-Task | untracked `create_task` | **`Runtime._refresh_task`** — im `aclose` gecancelt + abgewartet |
| `session_token` | Modul-Global | **`Runtime.session_token`** (per-App); WS/REST lesen `app.state.runtime` |
| `ws_clients` | Modul-Global | **`Runtime.ws_clients`** (per-App); WS liest `app.state.runtime` |
| `conversations`, `pending_confirm` | `assistant_core`-Globals | **`Runtime`** (per-App); `wire()` aliast die Modul-Globals darauf (Semantik unverändert) |
| Start-Verdrahtung (4× `configure`/`init_clients`) | Import | **`Runtime.wire()`** — einziger Aufrufer (D2), idempotent (`_wired`) |
| FastAPI-App | `app = FastAPI()` beim Import | **`create_app(runtime)`** — reine, seiteneffektfreie Verdrahtung; `app = create_app(runtime)` bleibt import-sicher |

## Verbleibende Modul-Globals (mit Begründung)

- **`server.config` / `server.CONFIG_PATH` / `server.STARTUP_WARNINGS`** — bewusst
  **A6-Residual** (Settings-Live-Apply = **Kandidat 05**, Nicht-Ziel dieses RFC).
  Der Lifespan spiegelt sie aus der aktiven Runtime; `apply_settings` mutiert sie
  weiter wie bisher (Wire-/Config-Vertrag unverändert).
- **`server.SESSION_TOKEN` / `server.ws_clients`** — Read-Spiegel der Runtime für
  Bestandsaufrufer; die sicherheitskritischen Pfade lesen bereits `app.state.runtime`.
- **`assistant_core`** Persona/City/TTS + Health-Cache, **`app_launcher.APPS/PROFILES/
  ACTIVE_PROFILE`**, **`memory.VAULT_PATH/INBOX_PATH`** — Speicher bleibt im Modul, der
  **Lifecycle-Owner ist die Runtime** (`wire()`); echte per-Modul-Isolation gehört zu
  K03/K05.
- **`browser_tools._pw/_browser/_context`** — D4-Residual (per-App-Browser später).

**Kosmetisches Restpunkt (P3, bewusst nicht im Checkpoint behoben):** `import anthropic`
und `import httpx` in `server.py` sind seit der Migration ungenutzt — der Client-Bau
lebt in `runtime.py`. Kein Funktions-, Sicherheits- oder Gate-Impact; das Entfernen
wäre eine Codeänderung außerhalb des freigegebenen Checkpoint-Scopes und gehört in
einen eigenen Aufräum-Slice.

**Keine neuen produktiven Modul-Globals** im migrierten Bereich: neu ist nur der eine
`runtime`-Handle; alle übrigen Namen existierten bereits.

## Ownership-Regeln

- **OWNED** = vom Root selbst erzeugt (`aopen`) ⇒ im `aclose` geschlossen.
- **BORROWED** = von außen injiziert (`Runtime.for_production(ai=…, http=…)`) ⇒ **nie**
  vom Root geschlossen (Test-Fakes bleiben intakt).
- „Du schließt, was du öffnest"; `_closed`-Latch macht `aclose` idempotent.

## Lifecycle- und Cleanup-Verhalten

**Öffnen (`aopen`):** Config laden (falls nötig) → OWNED-`http` → OWNED-`ai` → `wire()`
→ Refresh-Task (außer `JARVIS_SKIP_STARTUP_REFRESH`).
**Schließen (`aclose`, umgekehrt, jeder Schritt guarded):** Refresh-Task cancel+await →
`browser_tools.close()` → OWNED `http` → OWNED `ai` → `_closed=True`.
**Partial-Failure:** Schlägt `aopen` fehl, ruft der Lifespan `aclose` **vor** dem
Weiterreichen des Fehlers (durch einen Test belegt — der Fehler wurde dabei gefunden
und behoben). **Fails-closed:** ungültige Produktionsconfig ⇒ Lifespan-Start bricht ab;
`python server.py` beendet mit Exit 1 **vor** `uvicorn.run` (Launcher-Semantik erhalten).

## Kompatibilitätsadapter (dünn, dokumentiert)

| Adapter | Alter Aufrufer | Verhalten | Entfernungsbedingung |
|---|---|---|---|
| `app = create_app(runtime)` (Modul-`app`) | `server.app`, `uvicorn server:app`, `python server.py`, Launcher | dünner ASGI-Einstieg; erzeugt beim Import **keine** Ressource | **bleibt** (öffentlicher Entry) |
| `SESSION_TOKEN`/`ws_clients` (Read-Spiegel) | Bestandstests/Helfer | identische Werte der aktiven Runtime | wenn alle Leser `app.state.runtime` nutzen |
| `config`/`CONFIG_PATH`/`STARTUP_WARNINGS` (Modul-Global) | Routen + `test_*` | Source-of-Truth wie bisher; Lifespan spiegelt initial | **mit Kandidat 05** |
| `apply_settings`/`broadcast_*`/`persist_launcher_block` | Routen, `PERSIST_LAUNCHER` | unverändert in `server.py` (K05-Territorium) | mit Kandidat 05 |

Adapter enthalten **keine** eigene Businesslogik, besitzen keinen Zustand und ändern
kein Wire-Format.

## Testevidenz

| Prüfung | Ergebnis |
|---|---|
| `tests/test_composition_root.py` (neu, 18 Tests) | Import-Sicherheit (Subprozess), Factory, Isolation, Lifecycle — **grün**, **5× flakefrei** |
| `python -m unittest discover -s tests` | **525 Tests, OK** (vorher 507 + 18 neue) |
| `python scripts/smoke-test.py` | **grün, 0 unerwartete Skips** |
| Browser-E2E (11 Flows) · A11y (22/22) · Reduced Motion (16/16) | **grün** |
| **Visual-Regression** (bestätigte Baseline) | **grün** — keine UI-Regression |
| Windows-Native-Smokes (9/9) · `verify_phase4` (27/27) · `verify_phase5` (13/13) | **grün** |
| Leaks | 0 Zombie-Prozesse, 0 Playwright-Reste, 0 belegte Testports |

## Isolationsgrad (ehrlich)

`Runtime` isoliert **sofort**: `session_token`, `ws_clients`, `conversations`,
`pending_confirm`, `config`-Objekt, `ai`/`http`, App-Objekt/`app.state`, Lifespan —
belegt durch `RuntimeIsolationTests`. **Grenze:** Zustand, der noch als Modul-Global
via `configure()` lebt (Persona/City, `APPS/PROFILES`, `VAULT_PATH`, Health-Cache) sowie
die auf die Runtime **aliasierten** `assistant_core`-Dicts, wird von der jeweils zuletzt
verdrahteten Runtime bestimmt → **serielle** Isolation (Isolation in der Zeit), nicht
voll-parallel. Voll-parallele Isolation löst K03/K05 ein.

## Bewusst für Prompt 9 / später verschoben

- `protocol_version`, `event_id`, `correlation_id`, `schema_version`, State-Machines,
  Capability-/Policy-Kernel, Job-Engine/Scheduler, Config-Migrationen, strukturierte
  Logs (Prompt 9/10/11).
- **K05** (Settings-Single-Writer) → löst `config`/`apply_settings`-Residual.
- **K03** (Conversation-Session-deep-module) → voll-parallele Session-Isolation.
- **K04** (LLM-deep-module-Interface) · **D4** (per-App-Browser).
- **RFC-0001** (Action → deep module) — startet gemäß D1 **nach** diesem Root.
